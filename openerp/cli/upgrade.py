# Part of Odoo. See LICENSE file for full copyright and licensing details.
from __future__ import absolute_import

import sys
import json
from contextlib import contextmanager
from io import open
from os import makedirs, path, environ as ENV
from shutil import copyfileobj, copytree, rmtree
from argparse import ArgumentParser
from urllib import quote_plus
from time import sleep
from datetime import datetime
from logging import getLogger
from distutils.version import LooseVersion as Version
import subprocess
import random
import string
import base64

import openerp
from openerp import SUPERUSER_ID
from openerp.exceptions import UserError
from openerp.addons.base.ir.ir_attachment import ir_attachment
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from . import Command
from .server import main

__all__ = ['Upgrade']


CURRENT_VERSION = ".".join(map(str, openerp.release.version_info[:2]))
UPGRADE_URL = ENV.get('UPGRADE_URL', 'https://upgrade.odoo.com')
UPGRADE_INSECURE = bool(ENV.get('UPGRADE_INSECURE', False))
TEST_UPGRADE_WARNING = "This is a TEST upgrade database request, " \
                       "please DO NOT use this database for production " \
                       "purpose."


class Upgrade(Command):
    """
    Upgrade your old Odoo database to the latest.
    """

    argument_parser = ArgumentParser()
    argument_parser.add_argument('--dbname', '-d',
                                 required=True,
                                 help="Database to migrate")
    argument_parser.add_argument('--aim',
                                 default='test',
                                 choices=['test', 'production'],
                                 help="Upgrade aim")
    argument_parser.add_argument('--target', '--to',
                                 default=CURRENT_VERSION,
                                 help="Target version")
    argument_parser.add_argument('--postgresql', '--postgres', '--pg',
                                 help="PostgreSQL version")
    argument_parser.add_argument('--backup',
                                 default=None,
                                 action='store_true',
                                 help="Make a backup dump before migrating "
                                      "(default is 'yes' for production "
                                      "requests, no otherwise)")
    argument_parser.add_argument('--contract', '--enterprise',
                                 help="Odoo Enterprise contract")
    argument_parser.add_argument('--email',
                                 help="Contact Email")
    argument_parser.add_argument('--name',
                                 dest='destination',
                                 help="Migrated database name")
    argument_parser.add_argument('--run',
                                 action='store_true',
                                 help="Run the server when the process ends")
    argument_parser.add_argument('--restore',
                                 dest='request',
                                 type=int,
                                 help="Restore a specific upgrade request")
    argument_parser.add_argument('--key',
                                 help="Key for restoring a specific upgrade "
                                      "request")

    @contextmanager
    def _connect(self, dbname):
        db = openerp.sql_db.db_connect(dbname)
        with db.cursor() as cr:
            yield cr
        del db

    def _temp_name(self):
        return "__temp_" + "".join(random.choice(string.digits +
                                                 string.letters)
                                   for _ in range(4))

    def _find_pg_version(self, template='postgres'):
        """
        Determine PostgreSQL version
        """
        db = openerp.sql_db.db_connect(template)
        with db.cursor() as cr:
            # NOTE: do not use \d here. It doesn't work on Postgres 8.4
            #       (and probably others...)
            cr.execute(r"SELECT substring(version() from '[0-9]+\.[0-9]+');")
            version, = cr.fetchone()
        return version

    def _find_odoo_version(self, dbname):
        """
        Determine database's Odoo version
        """
        db = openerp.sql_db.db_connect(dbname)
        with db.cursor() as cr:
            cr.execute(r"""
                SELECT  substring(latest_version from '\d+\.\d+')
                FROM    ir_module_module
                WHERE   name = 'base';
                """)
            version, = cr.fetchone()
        return version

    def _minimifed_db(self, dbname, template='postgres'):
        """
        Move database attachments to the filestore
        """
        with self._connect(dbname) as cr:
            cr.execute("""\
                SELECT  1
                FROM    information_schema.columns
                WHERE   table_name = 'ir_attachment'
                AND     column_name = 'db_datas';
                """)
            db_datas_exists = cr.fetchone()
            if not db_datas_exists:
                cr.execute("""\
                    ALTER TABLE ir_attachment RENAME COLUMN datas TO db_datas;
                    """)
            cr.execute("""\
                SELECT  1
                FROM    ir_attachment
                WHERE   db_datas IS NOT NULL
                LIMIT 1;
                """)
            has_attachments_in_db = cr.fetchone()
        if not has_attachments_in_db:
            return None
        self._logger.info("Moving attachments to filestore...")
        min_db = self._temp_name()
        with self._connect(template) as cr:
            cr.autocommit(True)
            openerp.service.db._drop_conn(cr, dbname)
            cr.execute("CREATE DATABASE \"%s\" TEMPLATE \"%s\";"
                       % (min_db, dbname))
        with self._connect(dbname) as origin_cr:
            with self._connect(min_db) as cr:
                cr.execute("""
                    SELECT  1
                    FROM    information_schema.tables
                    WHERE   table_name = 'edi_document';
                    """)
                if cr.rowcount:
                    cr.execute("""
                        TRUNCATE TABLE edi_document;
                        """)
                for column, type_ in [('file_size', 'integer'),
                                      ('store_fname', 'varchar')]:
                    cr.execute("""\
                        SELECT  1
                        FROM    information_schema.columns
                        WHERE   table_name = 'ir_attachment'
                        AND     column_name = %s;
                        """, [column])
                    if not cr.rowcount:
                        cr.execute("""\
                            ALTER TABLE ir_attachment ADD COLUMN %s %s;
                            """ % (column, type_))
                obj = object.__new__(ir_attachment)
                iter_cur = cr._cnx.cursor("iter_cur")
                iter_cur.itersize = 1
                iter_cur.execute("""\
                    SELECT  id, db_datas
                    FROM    ir_attachment
                    WHERE   db_datas IS NOT NULL
                    FOR UPDATE;
                    """)
                for id, db_datas in iter_cur:
                    raw = base64.b64decode(db_datas)
                    checksum = obj._compute_checksum(raw)
                    fname, full_path = \
                        obj._get_path(origin_cr, SUPERUSER_ID, raw, checksum)
                    if not path.exists(full_path):
                        # NOTE: _file_write() hide exceptions, so we do it
                        #       ourselves
                        with open(full_path, 'wb') as fh:
                            fh.write(raw)
                    cr.execute("""
                        UPDATE  ir_attachment
                        SET     db_datas = NULL
                        ,       file_size = %s
                        ,       store_fname = %s
                        WHERE CURRENT OF iter_cur;
                        """, [len(raw), fname])
                cr.commit()
        return min_db

    def _replace_db(self, a, b):
        """
        Drop database a and put b in its shoes
        """
        openerp.sql_db.close_db(db_name)
        db = openerp.sql_db.db_connect('postgres')
        with db.cursor() as cr:
            cr.autocommit(True)
            openerp.service.db._drop_conn(cr, dbname)
            cr.execute("""
                DROP DATABASE "%(a)s";
                ALTER DATABASE "%(b)s" RENAME TO "%(a)s";
                """ % ())

    def _copy_filestore(self, a, b):
        """
        Copy filestore of database a to database b
        """
        filestore_path = openerp.tools.config.filestore(a)
        if path.isdir(filestore_path):
            self._logger.info("Copying filestore from database %s to %s...",
                              a, b)
            copytree(filestore_path, openerp.tools.config.filestore(b))

    def _restore_url(self, dbname, url):
        """
        Helper that restore the SQL from a specified URL to the existing
        database dbname.
        """
        # NOTE: -f make sure the process will fail with an exit code if the
        #       request doesn't succeed.
        command = self._make_request(url, args=['-f'])
        proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        try:
            command = ['psql', '-wX', '-v', 'ON_ERROR_STOP=1', dbname]
            stdin, stdout = openerp.tools.exec_pg_command_pipe(*command)
            stdout.close()
            try:
                copyfileobj(proc.stdout, stdin)
            finally:
                stdin.close()
            proc.stdout.close()
        except:
            try:
                proc.terminate()
            except OSError:
                pass
            raise
        finally:
            retcode = proc.wait()
        if not retcode == 0:
            raise subprocess.CalledProcessError(retcode, command)

    def backup(self, dbname):
        """
        Make an Odoo ZIP backup in the "backups" directory
        """
        backup_path = path.join(openerp.tools.config['data_dir'], 'backups')
        if not path.exists(backup_path):
            makedirs(backup_path)
        timestamp = datetime.now().strftime("%Y%m%d")
        dump_file = path.join(backup_path, "%s_%s.zip" % (dbname, timestamp))
        inc = 0
        while path.exists(dump_file):
            inc += 1
            dump_file = path.join(backup_path,
                                  "%s_%s_%d.zip" % (dbname, timestamp, inc))
        with open(dump_file, 'wb') as fh:
            openerp.service.db.dump_db(dbname, fh)
        self._logger.info("Database backup location: %s", dump_file)
        return dump_file

    def _make_request(self, url, params={}, args=[]):
        """
        Make an HTTP request using curl in command-line (because it's faster
        than requests)
        """
        command = ['curl', '-sSL'] + args
        if UPGRADE_INSECURE:
            command.append('-k')
        if url.startswith('/'):
            command.append(UPGRADE_URL + url)
        else:
            command.append(url)
        if params:
            command[-1] += "?%s" % "&".join("%s=%s" % (k, quote_plus(str(v)))
                                            for k, v in params.items()
                                            if v is not None)
        return command

    def _log_failures(self, response):
        """
        Log into the logger the failure messages of a response
        """
        for failure in response['failures']:
            self._logger.error("%s: %s", failure['reason'],
                               failure.get('message', 'none'))

    def upload_database(self, dbname, **params):
        """
        Upload SQL file object fh using the Odoo's upgrade API
        """
        command = self._make_request(
            "/database/v1/upgrade",
            params,
            args=['-H', "Content-Type: application/octet-stream",
                  '--data-binary', '@-'])
        proc = subprocess.Popen(command,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            dump_command = ['pg_dump', '-Ox', '-d', dbname]
            stdin, stdout = openerp.tools.exec_pg_command_pipe(*dump_command)
            stdin.close()
            copyfileobj(stdout, proc.stdin)
            proc.stdin.close()
        finally:
            retcode = proc.wait()
        if not retcode == 0:
            raise subprocess.CalledProcessError(retcode, command)
        response = json.loads(proc.stdout.read())
        return response

    def wait_request(self, **params):
        """
        Wait for an upgrade request to complete
        """
        command = self._make_request("/database/v1/status", params)
        state = 'pending'
        show_estimated_time = True
        show_testing = True
        while state in ['pending', 'processing', 'testing']:
            sleep(10)
            response = json.loads(subprocess.check_output(command))
            if response['failures']:
                self._log_failures(response)
                if 'SERVER:ERROR' not in \
                        [x['reason'] for x in response['failures']]:
                    raise UserError("Can not fetch request status")
            else:
                request = response['request']
                state = request['state']
                if request['estimated_time'] and show_estimated_time:
                    show_estimated_time &= False
                    self._logger.info(
                        "Estimated time: %s (calculated from your last "
                        "migration)", request['estimated_time'])
                if state == 'testing' and show_testing:
                    show_testing &= False
                    self._logger.info(
                        "Your database is being tested by our team. Please "
                        "be patient.")
                    self._logger.warn(
                        "This process can take a few days. You may want to "
                        "resume later. Hit Ctrl+C now to quit.")
        return request

    def upgrade(self, dbname, destination=None, backup=None, **params):
        """
        Upgrade database dbname and restore the upgraded database into
        destination, backup if required.

        If destination is the source database (dbname). The old database will
        be replaced by the migrated database and a backup of the old database
        will be done (except the flag backup is set to False).
        """
        postgresql = self._find_pg_version()
        if backup is None:
            backup = (params['aim'] == 'production')
        if not destination:
            if params['aim'] == 'production':
                destination = dbname
            else:
                timestamp = datetime.now().strftime("%Y%m%d")
                destination = "%s_migrated_%s_%s" \
                              % (dbname, params['target'], timestamp)
        source_version = self._find_odoo_version(dbname)
        self._logger.info("Odoo Database Upgrade started: %s -> %s",
                          source_version, params['target'])
        self._logger.info("Source database: %s", dbname)
        self._logger.info("Destination database: %s", destination)
        self._logger.info("PostgreSQL version: %s", params['postgresql'])
        self._logger.info("Aim: %s", params.get('aim', 'null'))
        self._logger.info("e-mail: %s", params.get('email', 'null'))
        self._logger.info("Odoo Enterprise contract: %s",
                          params.get('contract', 'null'))
        self._logger.info("Backup: %s", ('yes' if backup else 'no'))
        alt_name = self._temp_name() if destination == dbname else destination
        openerp.service.db._create_empty_database(alt_name)
        request = None
        min_db = None
        try:
            if backup:
                self.backup(dbname)
            # NOTE: do not attempt to move the attachments to the filestore for
            #       databases older than 7.0. The module 'document' need to be
            #       installed and set properly.
            if Version(params['target']) >= Version('7.0'):
                min_db = self._minimifed_db(dbname)
            if destination != dbname:
                self._copy_filestore(dbname, destination)
            response = self.upload_database((min_db if min_db else dbname),
                                            **params)
            if response['failures']:
                self._log_failures(response)
                raise UserError("Can not upload request to %s" % UPGRADE_URL)
            request = response['request']
            self._logger.info("Request: %d", request['id'])
            self._logger.info("Upgrade status page URL: %s",
                              request['status_url'])
            if not Version(request['postgresql']) <= Version(postgresql):
                raise UserError("Your version of PostgreSQL is incompatible. "
                                "You need at least PostgreSQL %s."
                                % request['postgresql'])
            self._logger.info("Waiting for database to get migrated...")
            request = self.wait_request(request=request['id'],
                                        key=request['key'])
            if request['state'] == 'invalid':
                raise UserError("Your upgrade request is invalid. Reasons: %s"
                                % request['customer_message'])
            elif request['state'] != 'done':
                raise UserError("Your database is not ready yet.")
            if request['filestore']:
                raise NotImplementedError(
                    "Filestore should have been migrated already")
            self._logger.info("Restoring upgraded database to %s...",
                              destination)
            if request['aim'] == 'test':
                self._logger.warn(TEST_UPGRADE_WARNING)
            self._restore_url(alt_name, request['migrated_sql_url'])
            # NOTE: Last but not least... you should never put code after this
            if destination == dbname:
                self._replace_db(dbname, alt_name)
        except:
            if request:
                self._logger.info(
                    "You can restore your upgraded database anytime using "
                    "this command: ./odoo.py upgrade --dbname '%s' "
                    "--restore %d --key '%s'", dbname, request['id'],
                    request['key'])
            openerp.service.db.exp_drop(alt_name)
            raise
        finally:
            if min_db:
                openerp.service.db.exp_drop(min_db)

    def restore(self, dbname, destination=None, backup=None, **params):
        """
        Restore an upgrade request to the databane dbname
        """
        postgresql = self._find_pg_version()
        if not dbname:
            raise UserError("Source database name is required")
        command = self._make_request("/database/v1/status", params)
        response = json.loads(subprocess.check_output(command))
        if response['failures']:
            self._log_failures(response)
            raise UserError("Can not get status of upgrade request")
        request = response['request']
        if backup is None:
            backup = (request['aim'] == 'production')
        if not destination:
            if request['aim'] == 'production':
                destination = dbname
            else:
                timestamp = datetime.strptime(request['processed_at'],
                                              DEFAULT_SERVER_DATETIME_FORMAT)\
                                    .strftime("%Y%m%d")
                destination = "%s_migrated_%s_%s" \
                              % (dbname, request['target'], timestamp)
        self._logger.info("Odoo Database Upgrade: %s -> %s",
                          request['database_version'], request['target'])
        self._logger.info("Processed at: %s", request['processed_at'])
        self._logger.info("Destination database: %s", destination)
        self._logger.info("Upgrade duration: %s", request['elapsed'])
        self._logger.info("Status page URL: %s", request['status_url'])
        self._logger.info("Backup: %s", ('yes' if backup else 'no'))
        if request['state'] == 'invalid':
            raise UserError("Your upgrade request is invalid. Reasons: %s"
                            % request['customer_message'])
        elif request['state'] != 'done':
            raise UserError("Your database is not ready yet.")
        if request['filestore']:
            raise NotImplementedError(
                "This upgrade request has a filestore")
        if not Version(request['postgresql']) <= Version(postgresql):
            raise UserError("Your version of PostgreSQL is incompatible. "
                            "You need at least PostgreSQL %s."
                            % request['postgresql'])
        if request['aim'] == 'test':
            self._logger.warn(TEST_UPGRADE_WARNING)
        openerp.service.db._create_empty_database(destination)
        try:
            if backup:
                self.backup(dbname)
            # NOTE: get the filestore from the source database
            self._copy_filestore(dbname, destination)
            self._logger.info("Restoring upgraded database to %s...",
                              destination)
            self._restore_url(destination, request['migrated_sql_url'])
        except:
            openerp.service.db.exp_drop(destination)
            raise

    def _parse_args(self, argv):
        args, extra = self.argument_parser.parse_known_args(argv)
        params = vars(args)
        if not params.get('postgresql'):
            params['postgresql'] = self._find_pg_version(params['dbname'])
            if not params['postgresql']:
                raise Exception("Can not determine PostgreSQL version")
        return (params, extra)

    def run(self, argv):
        params, extra = self._parse_args(argv)
        # NOTE: needed to load the parameters to connect to PostgreSQL and
        #       locate the filestore.
        openerp.tools.config.parse_config(extra)
        self._logger = getLogger('upgrade')
        try:
            if params['request']:
                self.restore(**params)
            else:
                self.upgrade(**params)
        except UserError as exc:
            self._logger.error(exc.name)
            return 1
        except openerp.service.db.DatabaseExists as exc:
            self._logger.error(exc.message)
            return 1
        except KeyboardInterrupt:
            return 0
        else:
            if params['run']:
                main(extra)
            return 0
