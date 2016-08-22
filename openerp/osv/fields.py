# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

""" Fields:
      - simple
      - relations (one2many, many2one, many2many)
      - function

    Fields Attributes:
        * _classic_read: is a classic sql fields
        * _type   : field type
        * _auto_join: for one2many and many2one fields, tells whether select
            queries will join the relational table instead of replacing the
            field condition by an equivalent-one based on a search.
        * readonly
        * required
        * size
"""

import base64
import datetime as DT
import functools
import logging
import pytz
import re
import xmlrpclib
from operator import itemgetter
from psycopg2 import Binary

import openerp
import openerp.tools as tools
from openerp.sql_db import LazyCursor
from openerp.tools.translate import _
from openerp.tools import float_repr, float_round, frozendict, html_sanitize
import json
from openerp import SUPERUSER_ID

# deprecated; kept for backward compatibility only
_get_cursor = LazyCursor

EMPTY_DICT = frozendict()

_logger = logging.getLogger(__name__)

def _symbol_set(symb):
    if symb is None or symb == False:
        return None
    elif isinstance(symb, unicode):
        return symb.encode('utf-8')
    return str(symb)


class _column(object):
    """ Base of all fields, a database column

        An instance of this object is a *description* of a database column. It will
        not hold any data, but only provide the methods to manipulate data of an
        ORM record or even prepare/update the database to hold such a field of data.
    """
    _classic_read = True
    _classic_write = True
    _auto_join = False
    _properties = False
    _type = 'unknown'
    _obj = None
    _multi = False
    _symbol_c = '%s'
    _symbol_f = _symbol_set
    _symbol_set = (_symbol_c, _symbol_f)
    _symbol_get = None
    _deprecated = False

    __slots__ = [
        'copy',                 # whether value is copied by BaseModel.copy()
        'string',
        'help',
        'required',
        'readonly',
        '_domain',
        '_context',
        'states',
        'priority',
        'change_default',
        'size',
        'ondelete',
        'translate',
        'select',
        'manual',
        'selectable',
        'group_operator',
        'groups',               # CSV list of ext IDs of groups
        'deprecated',           # Optional deprecation warning
        '_args',
        '_prefetch',
        '_module',              # the column's module name
    ]

    def __init__(self, string='unknown', required=False, readonly=False, domain=[], context={}, states=None, priority=0, change_default=False, size=None, ondelete=None, translate=False, select=False, manual=False, **args):
        """

        The 'manual' keyword argument specifies if the field is a custom one.
        It corresponds to the 'state' column in ir_model_fields.

        """
        # add parameters and default values
        args['copy'] = args.get('copy', True)
        args['string'] = string
        args['help'] = args.get('help', '')
        args['required'] = required
        args['readonly'] = readonly
        args['_domain'] = domain
        args['_context'] = context
        args['states'] = states
        args['priority'] = priority
        args['change_default'] = change_default
        args['size'] = size
        args['ondelete'] = ondelete.lower() if ondelete else None
        args['translate'] = translate
        args['select'] = select
        args['manual'] = manual
        args['selectable'] = args.get('selectable', True)
        args['group_operator'] = args.get('group_operator', None)
        args['groups'] = args.get('groups', None)
        args['deprecated'] = args.get('deprecated', None)
        args['_prefetch'] = args.get('_prefetch', True)
        args['_module'] = args.get('_module', None)

        self._args = EMPTY_DICT
        for key, val in args.iteritems():
            setattr(self, key, val)

        # prefetch only if _classic_write, not deprecated and not manual
        if not self._classic_write or self.deprecated or self.manual:
            self._prefetch = False

    def __getattr__(self, name):
        """ Access a non-slot attribute. """
        if name == '_args':
            raise AttributeError(name)
        try:
            return self._args[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        """ Set a slot or non-slot attribute. """
        try:
            object.__setattr__(self, name, value)
        except AttributeError:
            if self._args:
                self._args[name] = value
            else:
                self._args = {name: value}     # replace EMPTY_DICT

    def __delattr__(self, name):
        """ Remove a non-slot attribute. """
        try:
            del self._args[name]
        except KeyError:
            raise AttributeError(name)

    def new(self, _computed_field=False, **args):
        """ Return a column like `self` with the given parameters; the parameter
            `_computed_field` tells whether the corresponding field is computed.
        """
        # memory optimization: reuse self whenever possible; you can reduce the
        # average memory usage per registry by 10 megabytes!
        column = type(self)(**args)
        return self if self.to_field_args() == column.to_field_args() else column

    def to_field(self):
        """ convert column `self` to a new-style field """
        from openerp.fields import Field
        return Field.by_type[self._type](origin=self, **self.to_field_args())

    def to_field_args(self):
        """ return a dictionary with all the arguments to pass to the field """
        base_items = [
            ('_module', self._module),
            ('automatic', False),
            ('inherited', False),
            ('store', True),
            ('index', self.select),
            ('manual', self.manual),
            ('copy', self.copy),
            ('compute', None),
            ('inverse', None),
            ('search', None),
            ('related', None),
            ('string', self.string),
            ('help', self.help),
            ('readonly', self.readonly),
            ('required', self.required),
            ('states', self.states),
            ('groups', self.groups),
            ('change_default', self.change_default),
            ('deprecated', self.deprecated),
        ]
        truthy_items = filter(itemgetter(1), [
            ('group_operator', self.group_operator),
            ('size', self.size),
            ('ondelete', self.ondelete),
            ('translate', self.translate),
            ('domain', self._domain),
            ('context', self._context),
        ])
        return dict(base_items + truthy_items + self._args.items())

    def get(self, records, name, values=None):
        raise TypeError("Undefined method get() on field %s.%s." % (records._name, name))

    def set(self, record, name, value):
        setc, setf = self._symbol_set
        query = "UPDATE %s SET %s=%s WHERE id=%%s" % (record._table, name, setc)
        record._cr.execute(query, (setf(value), record.id))

    def search(self, model, args, name, value, offset=0, limit=None):
        domain = args + self._domain + [(name, 'ilike', value)]
        records = model.search(domain, offset=offset, limit=limit)
        return [vals[name] for vals in records.read([name])]

# ---------------------------------------------------------
# Simple fields
# ---------------------------------------------------------
class boolean(_column):
    _type = 'boolean'
    _symbol_c = '%s'
    _symbol_f = bool
    _symbol_set = (_symbol_c, _symbol_f)
    __slots__ = []

    def __init__(self, string='unknown', required=False, **args):
        super(boolean, self).__init__(string=string, required=required, **args)
        if required:
            _logger.debug(
                "required=True is deprecated: making a boolean field"
                " `required` has no effect, as NULL values are "
                "automatically turned into False. args: %r",args)

class integer(_column):
    _type = 'integer'
    _symbol_c = '%s'
    _symbol_f = lambda x: int(x or 0)
    _symbol_set = (_symbol_c, _symbol_f)
    _symbol_get = lambda self,x: x or 0
    __slots__ = []

    def __init__(self, string='unknown', required=False, **args):
        super(integer, self).__init__(string=string, required=required, **args)

class reference(_column):
    _type = 'reference'
    _classic_read = False # post-process to handle missing target
    __slots__ = ['selection']

    def __init__(self, string, selection, size=None, **args):
        if callable(selection):
            from openerp import api
            selection = api.expected(api.cr_uid_context, selection)
        _column.__init__(self, string=string, size=size, selection=selection, **args)

    def to_field_args(self):
        args = super(reference, self).to_field_args()
        args['selection'] = self.selection
        return args

    def get(self, records, name, values=None):
        result = {}
        # copy initial values fetched previously.
        for value in values:
            result[value['id']] = value[name]
            if value[name]:
                model, res_id = value[name].split(',')
                if not records.env[model].browse(int(res_id)).exists():
                    result[value['id']] = False
        return result

# takes a string (encoded in utf8) and returns a string (encoded in utf8)
def _symbol_set_char(self, symb):

    #TODO:
    # * we need to remove the "symb==False" from the next line BUT
    #   for now too many things rely on this broken behavior
    # * the symb==None test should be common to all data types
    if symb is None or symb == False:
        return None

    # we need to convert the string to a unicode object to be able
    # to evaluate its length (and possibly truncate it) reliably
    u_symb = tools.ustr(symb)
    return u_symb[:self.size].encode('utf8')

class char(_column):
    _type = 'char'
    __slots__ = ['_symbol_f', '_symbol_set', '_symbol_set_char']

    def __init__(self, string="unknown", size=None, **args):
        _column.__init__(self, string=string, size=size or None, **args)
        # self._symbol_set_char defined to keep the backward compatibility
        self._symbol_f = self._symbol_set_char = lambda x: _symbol_set_char(self, x)
        self._symbol_set = (self._symbol_c, self._symbol_f)

class text(_column):
    _type = 'text'
    __slots__ = []


class html(text):
    _type = 'html'
    _symbol_c = '%s'
    __slots__ = ['_sanitize', '_strip_style', '_strip_classes', '_symbol_f', '_symbol_set']

    def _symbol_set_html(self, value):
        if value is None or value is False:
            return None
        if not self._sanitize:
            return value
        return html_sanitize(value, silent=True, strict=True, strip_style=self._strip_style, strip_classes=self._strip_classes)

    def __init__(self, string='unknown', sanitize=True, strip_style=False, strip_classes=False, **args):
        super(html, self).__init__(string=string, **args)
        self._sanitize = sanitize
        self._strip_style = strip_style
        self._strip_classes = strip_classes
        # symbol_set redefinition because of sanitize specific behavior
        self._symbol_f = self._symbol_set_html
        self._symbol_set = (self._symbol_c, self._symbol_f)

    def to_field_args(self):
        args = super(html, self).to_field_args()
        args['sanitize'] = self._sanitize
        args['strip_style'] = self._strip_style
        args['strip_classes'] = self._strip_classes
        return args

import __builtin__

def _symbol_set_float(self, x):
    result = __builtin__.float(x or 0.0)
    digits = self.digits
    if digits:
        precision, scale = digits
        result = float_repr(float_round(result, precision_digits=scale), precision_digits=scale)
    return result

class float(_column):
    _type = 'float'
    _symbol_c = '%s'
    _symbol_get = lambda self,x: x or 0.0
    __slots__ = ['_digits', '_digits_compute', '_symbol_f', '_symbol_set']

    @property
    def digits(self):
        if self._digits_compute:
            with LazyCursor() as cr:
                return self._digits_compute(cr)
        else:
            return self._digits

    def __init__(self, string='unknown', digits=None, digits_compute=None, required=False, **args):
        _column.__init__(self, string=string, required=required, **args)
        # synopsis: digits_compute(cr) ->  (precision, scale)
        self._digits = digits
        self._digits_compute = digits_compute
        self._symbol_f = lambda x: _symbol_set_float(self, x)
        self._symbol_set = (self._symbol_c, self._symbol_f)

    def to_field_args(self):
        args = super(float, self).to_field_args()
        args['digits'] = self._digits_compute or self._digits
        return args

    def digits_change(self, cr):
        pass

def _symbol_set_monetary(val):
    try:
        return val.float_repr()         # see float_precision.float_repr()
    except Exception:
        return __builtin__.float(val or 0.0)

class monetary(_column):
    _type = 'monetary'
    _symbol_set = ('%s', _symbol_set_monetary)
    _symbol_get = lambda self,x: x or 0.0

    def to_field_args(self):
        raise NotImplementedError("fields.monetary is only supported in the new API, "
                                  "but you can use widget='monetary' in client-side views")

class date(_column):
    _type = 'date'
    __slots__ = []

    MONTHS = [
        ('01', 'January'),
        ('02', 'February'),
        ('03', 'March'),
        ('04', 'April'),
        ('05', 'May'),
        ('06', 'June'),
        ('07', 'July'),
        ('08', 'August'),
        ('09', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December')
    ]

    @staticmethod
    def today(*args):
        """ Returns the current date in a format fit for being a
        default value to a ``date`` field.

        This method should be provided as is to the _defaults dict, it
        should not be called.
        """
        return DT.date.today().strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)

    @staticmethod
    def context_today(model, cr, uid, context=None, timestamp=None):
        """Returns the current date as seen in the client's timezone
           in a format fit for date fields.
           This method may be passed as value to initialize _defaults.

           :param Model model: model (osv) for which the date value is being
                               computed - automatically passed when used in
                                _defaults.
           :param datetime timestamp: optional datetime value to use instead of
                                      the current date and time (must be a
                                      datetime, regular dates can't be converted
                                      between timezones.)
           :param dict context: the 'tz' key in the context should give the
                                name of the User/Client timezone (otherwise
                                UTC is used)
           :rtype: str 
        """
        today = timestamp or DT.datetime.now()
        context_today = None
        if context and context.get('tz'):
            tz_name = context['tz']  
        else:
            user = model.pool['res.users'].browse(cr, SUPERUSER_ID, uid)
            tz_name = user.tz
        if tz_name:
            try:
                utc = pytz.timezone('UTC')
                context_tz = pytz.timezone(tz_name)
                utc_today = utc.localize(today, is_dst=False) # UTC = no DST
                context_today = utc_today.astimezone(context_tz)
            except Exception:
                _logger.debug("failed to compute context/client-specific today date, "
                              "using the UTC value for `today`",
                              exc_info=True)
        return (context_today or today).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @staticmethod
    def date_to_datetime(model, cr, uid, userdate, context=None):
        """ Convert date values expressed in user's timezone to
        server-side UTC timestamp, assuming a default arbitrary
        time of 12:00 AM - because a time is needed.

        :param str userdate: date string in in user time zone
        :return: UTC datetime string for server-side use
        """
        user_date = DT.datetime.strptime(userdate, tools.DEFAULT_SERVER_DATE_FORMAT)
        if context and context.get('tz'):
            tz_name = context['tz']
        else:
            tz_name = model.pool.get('res.users').read(cr, SUPERUSER_ID, uid, ['tz'])['tz']
        if tz_name:
            utc = pytz.timezone('UTC')
            context_tz = pytz.timezone(tz_name)
            user_datetime = user_date + DT.timedelta(hours=12.0)
            local_timestamp = context_tz.localize(user_datetime, is_dst=False)
            user_datetime = local_timestamp.astimezone(utc)
            return user_datetime.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return user_date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)


class datetime(_column):
    _type = 'datetime'
    __slots__ = []

    MONTHS = [
        ('01', 'January'),
        ('02', 'February'),
        ('03', 'March'),
        ('04', 'April'),
        ('05', 'May'),
        ('06', 'June'),
        ('07', 'July'),
        ('08', 'August'),
        ('09', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December')
    ]

    @staticmethod
    def now(*args):
        """ Returns the current datetime in a format fit for being a
        default value to a ``datetime`` field.

        This method should be provided as is to the _defaults dict, it
        should not be called.
        """
        return DT.datetime.now().strftime(
            tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @staticmethod
    def context_timestamp(cr, uid, timestamp, context=None):
        """Returns the given timestamp converted to the client's timezone.
           This method is *not* meant for use as a _defaults initializer,
           because datetime fields are automatically converted upon
           display on client side. For _defaults you :meth:`fields.datetime.now`
           should be used instead.

           :param datetime timestamp: naive datetime value (expressed in UTC)
                                      to be converted to the client timezone
           :param dict context: the 'tz' key in the context should give the
                                name of the User/Client timezone (otherwise
                                UTC is used)
           :rtype: datetime
           :return: timestamp converted to timezone-aware datetime in context
                    timezone
        """
        assert isinstance(timestamp, DT.datetime), 'Datetime instance expected'
        if context and context.get('tz'):
            tz_name = context['tz']  
        else:
            registry = openerp.modules.registry.RegistryManager.get(cr.dbname)
            user = registry['res.users'].browse(cr, SUPERUSER_ID, uid)
            tz_name = user.tz
        utc_timestamp = pytz.utc.localize(timestamp, is_dst=False) # UTC = no DST
        if tz_name:
            try:
                context_tz = pytz.timezone(tz_name)
                return utc_timestamp.astimezone(context_tz)
            except Exception:
                _logger.debug("failed to compute context/client-specific timestamp, "
                              "using the UTC value",
                              exc_info=True)
        return utc_timestamp

class binary(_column):
    _type = 'binary'
    _classic_read = False
    _classic_write = property(lambda self: not self.attachment)

    # Binary values may be byte strings (python 2.6 byte array), but
    # the legacy OpenERP convention is to transfer and store binaries
    # as base64-encoded strings. The base64 string may be provided as a
    # unicode in some circumstances, hence the str() cast in symbol_f.
    # This str coercion will only work for pure ASCII unicode strings,
    # on purpose - non base64 data must be passed as a 8bit byte strings.
    _symbol_c = '%s'
    _symbol_f = lambda symb: symb and Binary(str(symb)) or None
    _symbol_set = (_symbol_c, _symbol_f)
    _symbol_get = lambda self, x: x and str(x)

    __slots__ = ['attachment', 'filters']

    def __init__(self, string='unknown', filters=None, **args):
        args['_prefetch'] = args.get('_prefetch', False)
        args['attachment'] = args.get('attachment', False)
        _column.__init__(self, string=string, filters=filters, **args)

    def to_field_args(self):
        args = super(binary, self).to_field_args()
        args['attachment'] = self.attachment
        return args

    def get(self, records, name, values=None):
        result = dict.fromkeys(records.ids, False)

        if self.attachment:
            # values are stored in attachments, retrieve them
            domain = [
                ('res_model', '=', records._name),
                ('res_field', '=', name),
                ('res_id', 'in', records.ids),
            ]
            for att in records.env['ir.attachment'].sudo().search(domain):
                # the 'bin_size' flag is handled by the field 'datas' itself
                result[att.res_id] = att.datas
        else:
            # If client is requesting only the size of the field, we return it
            # instead of the content. Presumably a separate request will be done
            # to read the actual content if it's needed at some point.
            context = records._context
            if context.get('bin_size') or context.get('bin_size_%s' % name):
                postprocess = lambda val: tools.human_size(long(val))
            else:
                postprocess = lambda val: val
            for val in (values or []):
                result[val['id']] = postprocess(val[name])

        return result

    def set(self, record, name, value):
        assert self.attachment
        # retrieve the attachment that stores the value, and adapt it
        domain = [
            ('res_model', '=', record._name),
            ('res_field', '=', name),
            ('res_id', '=', record.id),
        ]
        att = record.env['ir.attachment'].sudo().search(domain)
        with att.env.norecompute():
            if value:
                if att:
                    att.write({'datas': value})
                else:
                    att.create({
                        'name': name,
                        'res_model': record._name,
                        'res_field': name,
                        'res_id': record.id,
                        'type': 'binary',
                        'datas': value,
                    })
            else:
                att.unlink()
        return []

class selection(_column):
    _type = 'selection'
    __slots__ = ['selection']

    def __init__(self, selection, string='unknown', **args):
        if callable(selection):
            from openerp import api
            selection = api.expected(api.cr_uid_context, selection)
        _column.__init__(self, string=string, selection=selection, **args)

    def to_field_args(self):
        args = super(selection, self).to_field_args()
        args['selection'] = self.selection
        return args

    @classmethod
    def reify(cls, cr, uid, model, field, context=None):
        """ Munges the field's ``selection`` attribute as necessary to get
        something useable out of it: calls it if it's a function, applies
        translations to labels if it's not.

        A callable ``selection`` is considered translated on its own.

        :param orm.Model model:
        :param _column field:
        """
        if callable(field.selection):
            return field.selection(model, cr, uid, context)

        if not (context and 'lang' in context):
            return field.selection

        # field_to_dict isn't given a field name, only a field object, we
        # need to get the name back in order to perform the translation lookup
        field_name = next(
            name for name, column in model._columns.iteritems()
            if column == field)

        translation_filter = "%s,%s" % (model._name, field_name)
        translate = functools.partial(
            model.pool['ir.translation']._get_source,
            cr, uid, translation_filter, 'selection', context['lang'])

        return [
            (value, translate(label))
            for value, label in field.selection
        ]

# ---------------------------------------------------------
# Relationals fields
# ---------------------------------------------------------

#
# Values: (0, 0,  { fields })    create
#         (1, ID, { fields })    update
#         (2, ID)                remove (delete)
#         (3, ID)                unlink one (target id or target of relation)
#         (4, ID)                link
#         (5)                    unlink all (only valid for one2many)
#

class many2one(_column):
    _classic_read = False
    _classic_write = True
    _type = 'many2one'
    _symbol_c = '%s'
    _symbol_f = lambda x: x or None
    _symbol_set = (_symbol_c, _symbol_f)

    __slots__ = ['_obj', '_auto_join']

    def __init__(self, obj, string='unknown', auto_join=False, **args):
        args['ondelete'] = args.get('ondelete', 'set null')
        _column.__init__(self, string=string, **args)
        self._obj = obj
        self._auto_join = auto_join

    def to_field_args(self):
        args = super(many2one, self).to_field_args()
        args['comodel_name'] = self._obj
        args['auto_join'] = self._auto_join
        return args

    def set(self, record, name, value):
        comodel = record.env[self._obj]
        cr = record._cr
        if isinstance(value, list):
            for act in value:
                if act[0] == 0:
                    line = comodel.create(act[2])
                    cr.execute("UPDATE %s SET %s=%%s WHERE id=%%s" % (record._table, name),
                               (line.id, record.id))
                elif act[0] == 1:
                    comodel.browse(act[1]).write(act[2])
                elif act[0] == 2:
                    cr.execute("DELETE FROM %s WHERE id=%%s" % comodel._table, (act[1],))
                elif act[0] in (3, 5):
                    cr.execute("UPDATE %s SET %s=NULL WHERE id=%%s" % (record._table, name),
                               (record.id,))
                elif act[0] == 4:
                    cr.execute("UPDATE %s SET %s=%%s WHERE id=%%s" % (record._table, name),
                               (act[1], record.id))
        else:
            if value:
                cr.execute("UPDATE %s SET %s=%%s WHERE id=%%s" % (record._table, name), (value, record.id))
            else:
                cr.execute("UPDATE %s SET %s=NULL WHERE id=%%s" % (record._table, name), (record.id,))

    def search(self, model, args, name, value, offset=0, limit=None):
        domain = args + self._domain + [('name', 'like', value)]
        return model.env[self._obj].search(domain, offset=offset, limit=limit).ids


class one2many(_column):
    _classic_read = False
    _classic_write = False
    _type = 'one2many'

    __slots__ = ['_obj', '_fields_id', '_limit', '_auto_join']

    def __init__(self, obj, fields_id, string='unknown', limit=None, auto_join=False, **args):
        # one2many columns are not copied by default
        args['copy'] = args.get('copy', False)
        args['_prefetch'] = args.get('_prefetch', False)
        _column.__init__(self, string=string, **args)
        self._obj = obj
        self._fields_id = fields_id
        self._limit = limit
        self._auto_join = auto_join
        #one2many can't be used as condition for defaults
        assert(self.change_default != True)

    def to_field_args(self):
        args = super(one2many, self).to_field_args()
        args['comodel_name'] = self._obj
        args['inverse_name'] = self._fields_id
        args['auto_join'] = self._auto_join
        args['limit'] = self._limit
        return args

    def get(self, records, name, values=None):
        if self._context:
            records = records.with_context(**self._context)

        # retrieve the records in the comodel
        comodel = records.env[self._obj]
        inverse = self._fields_id
        domain = self._domain(records) if callable(self._domain) else self._domain
        domain = domain + [(inverse, 'in', records.ids)]
        lines = comodel.search(domain, limit=self._limit)

        result = {id: [] for id in records.ids}
        # read the inverse of records without prefetching other fields on them
        for line in lines.with_context(prefetch_fields=False):
            # line[inverse] may be a record or an integer
            result[int(line[inverse])].append(line.id)

        return result

    def set(self, record, name, value):
        if not value:
            return
        result = []
        cr = record._cr
        comodel = record.env[self._obj].with_context(**self._context)
        with comodel.env.norecompute():
            for act in value:
                if act[0] == 0:
                    act[2][self._fields_id] = record.id
                    comodel.create(act[2])
                elif act[0] == 1:
                    comodel.browse(act[1]).write(act[2])
                elif act[0] == 2:
                    comodel.browse(act[1]).unlink()
                elif act[0] == 3:
                    inverse_field = comodel._fields.get(self._fields_id)
                    assert inverse_field, 'Trying to unlink the content of a o2m but the pointed model does not have a m2o'
                    # if the model has on delete cascade, just delete the row
                    if inverse_field.ondelete == "cascade":
                        comodel.browse(act[1]).unlink()
                    else:
                        cr.execute("UPDATE %s SET %s=NULL WHERE id=%%s" % (comodel._table, self._fields_id),
                                   (act[1],))
                elif act[0] == 4:
                    # check whether the given record is already linked
                    line = comodel.browse(act[1])
                    line_sudo = line.sudo().with_context(prefetch_fields=False)
                    if int(line_sudo[self._fields_id]) != record.id:
                        # Must use write() to recompute parent_store structure if needed and check access rules
                        line.write({self._fields_id: record.id})
                elif act[0] == 5:
                    inverse_field = comodel._fields.get(self._fields_id)
                    assert inverse_field, 'Trying to unlink the content of a o2m but the pointed model does not have a m2o'
                    # if the o2m has a static domain we must respect it when unlinking
                    domain = self._domain(comodel) if callable(self._domain) else self._domain
                    extra_domain = domain or []
                    lines = comodel.search([(self._fields_id, '=', record.id)] + extra_domain)
                    # If the model has cascade deletion, we delete the rows because it is the intended behavior,
                    # otherwise we only nullify the reverse foreign key column.
                    if inverse_field.ondelete == "cascade":
                        lines.unlink()
                    else:
                        lines.write({self._fields_id: False})
                elif act[0] == 6:
                    # Must use write() to recompute parent_store structure if needed
                    comodel.browse(act[2]).write({self._fields_id: record.id})
                    cr.execute("SELECT id FROM %s WHERE %s=%%s AND id <> ALL(%%s)" % (comodel._table, self._fields_id),
                               (record.id, act[2] or [0]))
                    lines = comodel.browse([row[0] for row in cr.fetchall()])
                    lines.write({self._fields_id: False})
        return result

    def search(self, model, args, name, value, offset=0, limit=None, operator='ilike'):
        domain = self._domain(model) if callable(self._domain) else self._domain
        return model.env[self._obj].name_search(value, domain, operator, limit=limit)

#
# Values: (0, 0,  { fields })    create
#         (1, ID, { fields })    update (write fields to ID)
#         (2, ID)                remove (calls unlink on ID, that will also delete the relationship because of the ondelete)
#         (3, ID)                unlink (delete the relationship between the two objects but does not delete ID)
#         (4, ID)                link (add a relationship)
#         (5, ID)                unlink all
#         (6, ?, ids)            set a list of links
#
class many2many(_column):
    """Encapsulates the logic of a many-to-many bidirectional relationship, handling the
       low-level details of the intermediary relationship table transparently.
       A many-to-many relationship is always symmetrical, and can be declared and accessed
       from either endpoint model.
       If ``rel`` (relationship table name), ``id1`` (source foreign key column name)
       or id2 (destination foreign key column name) are not specified, the system will
       provide default values. This will by default only allow one single symmetrical
       many-to-many relationship between the source and destination model.
       For multiple many-to-many relationship between the same models and for
       relationships where source and destination models are the same, ``rel``, ``id1``
       and ``id2`` should be specified explicitly.

       :param str obj: destination model
       :param str rel: optional name of the intermediary relationship table. If not specified,
                       a canonical name will be derived based on the alphabetically-ordered
                       model names of the source and destination (in the form: ``amodel_bmodel_rel``).
                       Automatic naming is not possible when the source and destination are
                       the same, for obvious ambiguity reasons.
       :param str id1: optional name for the column holding the foreign key to the current
                       model in the relationship table. If not specified, a canonical name
                       will be derived based on the model name (in the form: `src_model_id`).
       :param str id2: optional name for the column holding the foreign key to the destination
                       model in the relationship table. If not specified, a canonical name
                       will be derived based on the model name (in the form: `dest_model_id`)
       :param str string: field label
    """
    _classic_read = False
    _classic_write = False
    _type = 'many2many'

    __slots__ = ['_obj', '_rel', '_id1', '_id2', '_limit', '_auto_join']

    def __init__(self, obj, rel=None, id1=None, id2=None, string='unknown', limit=None, **args):
        """
        """
        args['_prefetch'] = args.get('_prefetch', False)
        _column.__init__(self, string=string, **args)
        self._obj = obj
        if rel and '.' in rel:
            raise Exception(_('The second argument of the many2many field %s must be a SQL table !'\
                'You used %s, which is not a valid SQL table name.')% (string,rel))
        self._rel = rel
        self._id1 = id1
        self._id2 = id2
        self._limit = limit
        self._auto_join = False

    def to_field_args(self):
        args = super(many2many, self).to_field_args()
        args['comodel_name'] = self._obj
        args['relation'] = self._rel
        args['column1'] = self._id1
        args['column2'] = self._id2
        args['auto_join'] = self._auto_join
        args['limit'] = self._limit
        return args

    def _sql_names(self, source_model):
        """Return the SQL names defining the structure of the m2m relationship table

            :return: (m2m_table, local_col, dest_col) where m2m_table is the table name,
                     local_col is the name of the column holding the current model's FK, and
                     dest_col is the name of the column holding the destination model's FK, and
        """
        tbl, col1, col2 = self._rel, self._id1, self._id2
        if not all((tbl, col1, col2)):
            # the default table name is based on the stable alphabetical order of tables
            dest_model = source_model.pool[self._obj]
            tables = tuple(sorted([source_model._table, dest_model._table]))
            if not tbl:
                assert tables[0] != tables[1], 'Implicit/Canonical naming of m2m relationship table '\
                                               'is not possible when source and destination models are '\
                                               'the same'
                tbl = '%s_%s_rel' % tables
                openerp.models.check_pg_name(tbl)
            if not col1:
                col1 = '%s_id' % source_model._table
            if not col2:
                col2 = '%s_id' % dest_model._table
        return tbl, col1, col2

    def _get_query_and_where_params(self, records, values, where_params):
        """ Extracted from ``get`` to facilitate fine-tuning of the generated
            query. """
        query = """SELECT %(rel)s.%(id2)s, %(rel)s.%(id1)s
                     FROM %(rel)s, %(from_c)s
                    WHERE %(where_c)s
                      AND %(rel)s.%(id1)s IN %%s
                      AND %(rel)s.%(id2)s = %(tbl)s.id
                      %(order_by)s
                      %(limit)s
                   OFFSET %(offset)d
                """ % values
        return query, where_params + [tuple(records.ids)]

    def get(self, records, name, values=None):
        if not records:
            return {}
        comodel = records.env[self._obj]
        rel, id1, id2 = self._sql_names(records)

        # static domains are lists, and are evaluated both here and on client-side, while string
        # domains supposed by dynamic and evaluated on client-side only (thus ignored here)
        # FIXME: make this distinction explicit in API!
        domain = isinstance(self._domain, list) and self._domain or []

        wquery = comodel._where_calc(domain)
        comodel._apply_ir_rules(wquery, 'read')
        order_by = comodel._generate_order_by(None, wquery)
        from_c, where_c, where_params = wquery.get_sql()
        if not where_c:
            where_c = '1=1'

        limit_str = ''
        if self._limit is not None:
            limit_str = ' LIMIT %d' % self._limit

        query_parts = {
            'rel': rel,
            'id1': id1,
            'id2': id2,
            'tbl': comodel._table,
            'from_c': from_c,
            'where_c': where_c,
            'limit': limit_str,
            'offset': 0,
            'order_by': order_by,
        }
        query, where_params = self._get_query_and_where_params(records, query_parts, where_params)
        records._cr.execute(query, where_params)
        res = {id: [] for id in records.ids}
        for row in records._cr.fetchall():
            res[row[1]].append(row[0])
        return res

    def set(self, record, name, value):
        if not value:
            return
        cr = record._cr
        rel, id1, id2 = self._sql_names(record)
        comodel = record.env[self._obj]

        def link(ids):
            # beware of duplicates when inserting
            query = """ INSERT INTO {rel} ({id1}, {id2})
                        (SELECT %s, unnest(%s)) EXCEPT (SELECT {id1}, {id2} FROM {rel} WHERE {id1}=%s)
                    """.format(rel=rel, id1=id1, id2=id2)
            for sub_ids in cr.split_for_in_conditions(ids):
                cr.execute(query, (record.id, list(sub_ids), record.id))

        def unlink_all():
            # remove all records for which user has access rights
            clauses, params, tables = comodel.env['ir.rule'].domain_get(comodel._name)
            cond = " AND ".join(clauses) if clauses else "1=1"
            query = """ DELETE FROM {rel} USING {tables}
                        WHERE {rel}.{id1}=%s AND {rel}.{id2}={table}.id AND {cond}
                    """.format(rel=rel, id1=id1, id2=id2,
                               table=comodel._table, tables=','.join(tables), cond=cond)
            cr.execute(query, [record.id] + params)

        for act in value:
            if not isinstance(act, (list, tuple)) or not act:
                continue
            if act[0] == 0:
                line = comodel.create(act[2])
                cr.execute("INSERT INTO %s(%s,%s) VALUES (%%s,%%s)" % (rel, id1, id2), (record.id, line.id))
            elif act[0] == 1:
                comodel.browse(act[1]).write(act[2])
            elif act[0] == 2:
                comodel.browse(act[1]).unlink()
            elif act[0] == 3:
                cr.execute("DELETE FROM %s WHERE %s=%%s AND %s=%%s" % (rel, id1, id2), (record.id, act[1]))
            elif act[0] == 4:
                link([act[1]])
            elif act[0] == 5:
                unlink_all()
            elif act[0] == 6:
                unlink_all()
                link(act[2])

    #
    # TODO: use a name_search
    #
    def search(self, model, args, name, value, offset=0, limit=None, operator='ilike'):
        domain = args + self._domain + [('name', operator, value)]
        return model.env[self._obj].search(domain, offset=offset, limit=limit)


def get_nice_size(value):
    size = 0
    if isinstance(value, (int,long)):
        size = value
    elif value: # this is supposed to be a string
        size = len(value)
        if size < 12:  # suppose human size
            return value
    return tools.human_size(size)

# See http://www.w3.org/TR/2000/REC-xml-20001006#NT-Char
# and http://bugs.python.org/issue10066
invalid_xml_low_bytes = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]')

def sanitize_binary_value(value):
    # binary fields should be 7-bit ASCII base64-encoded data,
    # but we do additional sanity checks to make sure the values
    # are not something else that won't pass via XML-RPC
    if isinstance(value, (xmlrpclib.Binary, tuple, list, dict)):
        # these builtin types are meant to pass untouched
        return value

    # Handle invalid bytes values that will cause problems
    # for XML-RPC. See for more info:
    #  - http://bugs.python.org/issue10066
    #  - http://www.w3.org/TR/2000/REC-xml-20001006#NT-Char

    # Coercing to unicode would normally allow it to properly pass via
    # XML-RPC, transparently encoded as UTF-8 by xmlrpclib.
    # (this works for _any_ byte values, thanks to the fallback
    #  to latin-1 passthrough encoding when decoding to unicode)
    value = tools.ustr(value)

    # Due to Python bug #10066 this could still yield invalid XML
    # bytes, specifically in the low byte range, that will crash
    # the decoding side: [\x00-\x08\x0b-\x0c\x0e-\x1f]
    # So check for low bytes values, and if any, perform
    # base64 encoding - not very smart or useful, but this is
    # our last resort to avoid crashing the request.
    if invalid_xml_low_bytes.search(value):
        # b64-encode after restoring the pure bytes with latin-1
        # passthrough encoding
        value = base64.b64encode(value.encode('latin-1'))

    return value


# ---------------------------------------------------------
# Serialized fields
# ---------------------------------------------------------

class serialized(_column):
    """ A field able to store an arbitrary python data structure.
    
        Note: only plain components allowed.
    """
    _type = 'serialized'
    __slots__ = []

    def _symbol_set_struct(val):
        return json.dumps(val)

    def _symbol_get_struct(self, val):
        return json.loads(val or '{}')

    _symbol_c = '%s'
    _symbol_f = _symbol_set_struct
    _symbol_set = (_symbol_c, _symbol_f)
    _symbol_get = _symbol_get_struct

    def __init__(self, *args, **kwargs):
        kwargs['_prefetch'] = kwargs.get('_prefetch', False)
        super(serialized, self).__init__(*args, **kwargs)


class column_info(object):
    """ Struct containing details about an osv column, either one local to
        its model, or one inherited via _inherits.

        .. attribute:: name

            name of the column

        .. attribute:: column

            column instance, subclass of :class:`_column`

        .. attribute:: parent_model

            if the column is inherited, name of the model that contains it,
            ``None`` for local columns.

        .. attribute:: parent_column

            the name of the column containing the m2o relationship to the
            parent model that contains this column, ``None`` for local columns.

        .. attribute:: original_parent

            if the column is inherited, name of the original parent model that
            contains it i.e in case of multilevel inheritance, ``None`` for
            local columns.
    """
    __slots__ = ['name', 'column', 'parent_model', 'parent_column', 'original_parent']

    def __init__(self, name, column, parent_model=None, parent_column=None, original_parent=None):
        self.name = name
        self.column = column
        self.parent_model = parent_model
        self.parent_column = parent_column
        self.original_parent = original_parent

    def __str__(self):
        return '%s(%s, %s, %s, %s, %s)' % (
            self.__class__.__name__, self.name, self.column,
            self.parent_model, self.parent_column, self.original_parent)
