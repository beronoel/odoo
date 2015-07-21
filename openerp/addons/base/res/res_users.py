# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import itertools
import logging
from functools import partial
from itertools import repeat

from lxml import etree
from lxml.builder import E

import openerp
from openerp import api, fields, models, SUPERUSER_ID, _
# from openerp import SUPERUSER_ID, models
from openerp import tools
import openerp.exceptions
from openerp.osv import expression
from openerp.exceptions import UserError

_logger = logging.getLogger(__name__)

# Only users who can modify the user (incl. the user herself) see the real contents of these fields
USER_PRIVATE_FIELDS = ['password']

#----------------------------------------------------------
# Basic res.groups and res.users
#----------------------------------------------------------


class ResGroups(models.Model):
    _name = "res.groups"
    _description = "Access Groups"
    _rec_name = 'full_name'
    _order = 'name'

    @api.multi
    def _get_full_name(self):
        res = {}
        for record in self:
            if record.category_id:
                res[record.id] = '%s / %s' % (record.category_id.name, record.name)
            else:
                res[record.id] = record.name
        return res

    @api.multi
    def _search_group(self, args):
        operand = args[0][2]
        operator = args[0][1]
        lst = True
        if isinstance(operand, bool):
            domains = [[('name', operator, operand)], [('category_id.name', operator, operand)]]
            if operator in expression.NEGATIVE_TERM_OPERATORS == (not operand):
                return expression.AND(domains)
            else:
                return expression.OR(domains)
        if isinstance(operand, basestring):
            lst = False
            operand = [operand]
        where = []
        for group in operand:
            values = filter(bool, group.split('/'))
            group_name = values.pop().strip()
            category_name = values and '/'.join(values).strip() or group_name
            group_domain = [('name', operator, lst and [group_name] or group_name)]
            category_domain = [
                ('category_id.name', operator, lst and [category_name] or category_name)]
            if operator in expression.NEGATIVE_TERM_OPERATORS and not values:
                category_domain = expression.OR([category_domain, [('category_id', '=', False)]])
            if (operator in expression.NEGATIVE_TERM_OPERATORS) == (not values):
                sub_where = expression.AND([group_domain, category_domain])
            else:
                sub_where = expression.OR([group_domain, category_domain])
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                where = expression.AND([where, sub_where])
            else:
                where = expression.OR([where, sub_where])
        return where

    name = fields.Char(required=True, translate=True)
    users = fields.Many2many('res.users', 'res_groups_users_rel', 'gid', 'uid')
    model_access = fields.One2many('ir.model.access', 'group_id',
                                   string='Access Controls', copy=True)
    rule_groups = fields.Many2many('ir.rule', 'rule_group_rel', 'group_id', 'rule_group_id',
                                   string='Rules', domain=[('global', '=', False)])
    menu_access = fields.Many2many('ir.ui.menu', 'ir_ui_menu_group_rel', 'gid', 'menu_id',
                                   string='Access Menu')
    view_access = fields.Many2many('ir.ui.view', 'ir_ui_view_group_rel', 'group_id', 'view_id',
                                   string='Views')
    comment = fields.Text(translate=True)
    category_id = fields.Many2one('ir.module.category', string='Application', index=True)
    full_name = fields.Char(compute='_get_full_name', string='Group Name', search=_search_group)
    share = fields.Boolean(
        string='Share Group',
        help="Group created to set access rights for sharing data with some users.")

    _sql_constraints = [
        ('name_uniq', 'unique (category_id, name)',
            _('The name of the group must be unique within an application!'))
    ]

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # add explicit ordering if search is sorted on full_name
        if order and order.startswith('full_name'):
            self.sort(key=lambda g: g.full_name, reverse=order.endswith('DESC'))
            self = self[offset:offset+limit] if limit else self[offset:]
            return map(int, self)
        return super(ResGroups, self).search(args, offset, limit, order, count=count)

    @api.one
    def copy(self, default=None):
        group_name = self.read(['name'])[0]['name']
        default.update({'name': _('%s (copy)') % group_name})
        return super(ResGroups, self).copy(default)

    @api.multi
    def write(self, vals):
        if 'name' in vals:
            if vals['name'].startswith('-'):
                raise UserError(_('The name of the group can not start with "-"'))
        res = super(ResGroups, self).write(vals)
        self.env['ir.model.access'].call_cache_clearing_methods()
        self.env['res.users'].has_group_wrapper.clear_cache(self.env['res.users'])
        return res


class ResUsers(models.Model):
    """ User class. A res.users record models an OpenERP user and is different
        from an employee.

        res.users class now inherits from res.partner. The partner model is
        used to store the data related to the partner: lang, name, address,
        avatar, ... The user model is now dedicated to technical data.
    """
    __admin_ids = {}
    _uid_cache = {}
    _inherits = {
        'res.partner': 'partner_id',
    }
    _name = "res.users"
    _description = 'Users'

    def _set_new_password(self, value, args):
        if value is False:
            # Do not update the password if no value is provided, ignore silently.
            # For example web client submits False values for all empty fields.
            return
        if self.env.user.id == self.id:
            # To change their own password users must use the client-specific change password wizard,
            # so that the new password is immediately used for further RPC requests, otherwise the user
            # will face unexpected 'Access Denied' exceptions.
            raise UserError(_('Please use the change password wizard (in User Preferences or User menu) to change your own password.'))
        self.write({'password': value})

    @api.multi
    def _get_password(self):
        return dict.fromkeys(self.ids, '')

    @api.multi
    def _is_share(self):
        for user in self:
            self.id = not user.has_group_wrapper('base.group_user')

    @api.depends('share')
    def _get_users_from_group(self):
        result = set()
        groups = self.env['res.groups'].browse()
        # Clear cache to avoid perf degradation on databases with thousands of users
        groups.invalidate_cache()
        for group in groups:
            result.update(user.id for user in group.users)
        return list(result)

    def _get_company(self, uid2=False):
        if not uid2:
            uid2 = self.env.user
        return uid2.company_id

    def _get_companies(self):
        company = self._get_company()
        if company:
            return company.ids

    def _get_group(self):
        result = []
        try:
            group_id = self.env.ref('base.group_user').id
            result.append(group_id)
            group_id = self.env.ref('base.group_partner_manager').id
            result.append(group_id)
        except ValueError:
            # If these groups does not exists anymore
            pass
        return result

    @api.onchange('login')
    def on_change_login(self):
        if self.login and tools.single_email_re.match(self.login):
            self.email = self.login

    @api.onchange('state_id')
    def onchange_state(self):
        partners = [user.partner_id for user in self]
        return partners.onchange_state(self.state_id)

    @api.onchange('is_company')
    def onchange_type(self):
        """ Wrapper on the user.partner onchange_type, because some calls to the
            partner form view applied to the user may trigger the
            partner.onchange_type method, but applied to the user object.
        """
        partners = [user.partner_id for user in self]
        return partners.onchange_type(self.is_company)

    @api.onchange('use_parent_address', 'parent_id')
    def onchange_address(self):
        """ Wrapper on the user.partner onchange_address, because some calls to the
            partner form view applied to the user may trigger the
            partner.onchange_type method, but applied to the user object.
        """
        partners = [user.partner_id for user in self]
        return partners.onchange_address(self.use_parent_address, self.parent_id)

    @api.depends('company_id', 'company_ids')
    def _check_company(self):
        for user in self:
            if (user.company_id in user.company_ids) or not user.company_ids:
                return _('The chosen company is not in the allowed companies for this user')

    id = fields.Integer()
    login_date = fields.Datetime(string='Latest connection', index=True, copy=False)
    partner_id = fields.Many2one('res.partner', required=True,
                                 string='Related Partner', ondelete='restrict',
                                 help='Partner-related data of the user', auto_join=True)
    login = fields.Char(required=True,
                        help="Used to log into the system")
    password = fields.Char(
        invisible=True, copy=False, default='',
        help="Keep empty if you don't want the user to be able to connect on the system.")
    new_password = fields.Char(
        compute='_get_password',
        inverse='_set_new_password', string='Set Password',
        help="Specify a value only when creating a user or if you're "
             "changing the user's password, otherwise leave empty. After "
             "a change of password, the user has to login again.")
    signature = fields.Html()
    active = fields.Boolean(default=True)
    action_id = fields.Many2one('ir.actions.actions', string='Home Action',
        help="If specified, this action will be opened at log on for this user, in addition to the standard menu.")
    groups_id = fields.Many2many('res.groups', 'res_groups_users_rel', 'uid', 'gid',
                                 default=_get_group,
                                 string='Groups')
    # Special behavior for this field: res.company.search() will only return the companies
    # available to the current user (should be the user's companies?), when the user_preference
    # context is set.
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=_get_company,
                                 help='The company this user is currently working for.',
                                 context={'user_preference': True})
    company_ids = fields.Many2many('res.company', 'res_company_users_rel', 'user_id', 'cid',
                                   default=_get_companies,
                                   string='Companies')
    share = fields.Boolean(
        compute='_is_share', string='Share User', type='boolean',
        help="External user with limited access, created only for the purpose of sharing data.")

    # overridden inherited fields to bypass access rights, in case you have
    # access to the user but not its corresponding partner
    name = fields.Char(related='partner_id.name', inherited=True)
    email = fields.Char(related='partner_id.email', inherited=True)

    _sql_constraints = [
        ('login_key', 'UNIQUE (login)', _('You can not have two users with the same login !'))
    ]

    # User can write on a few of his own fields (but not his groups for example)
    SELF_WRITEABLE_FIELDS = ['password', 'signature', 'action_id', 'company_id', 'email',
                             'name', 'image', 'image_medium', 'image_small', 'lang', 'tz']
    # User can read a few of his own fields
    SELF_READABLE_FIELDS = ['signature', 'company_id', 'login', 'email', 'name', 'image',
                            'image_medium', 'image_small', 'lang', 'tz', 'tz_offset', 'groups_id',
                            'partner_id', '__last_update', 'action_id']

    @api.model
    def read(self, fields=None, load='_classic_read'):
        def override_password(o):
            if ('id' not in o or o['id'] != self.env.user.id):
                for f in USER_PRIVATE_FIELDS:
                    if f in o:
                        o[f] = '********'
            return o

        if fields and (self.ids == [self.env.user.id] or self.ids == self.env.user.id):
            for key in fields:
                if not (key in self.SELF_READABLE_FIELDS or key.startswith('context_')):
                    break
            else:
                # safe fields only, so we read as super-user to bypass access rights
                self = self.sudo()

        result = super(ResUsers, self).read(fields=fields, load=load)
        canwrite = self.env['ir.model.access'].check('res.users', 'write', False)
        if not canwrite:
            if isinstance(self.ids, (int, long)):
                result = override_password(result)
            else:
                result = map(override_password, result)

        return result

    @api.model
    def create(self, vals):
        user = super(ResUsers, self).create(vals)
        if user.partner_id.company_id:
            user.partner_id.write({'company_id': user.company_id.id})
        return user

    def write(self, cr, uid, ids, values, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        if ids == [uid]:
            for key in values.keys():
                if not (key in self.SELF_WRITEABLE_FIELDS or key.startswith('context_')):
                    break
            else:
                if 'company_id' in values:
                    user = self.browse(cr, SUPERUSER_ID, uid, context=context)
                    if not (values['company_id'] in user.company_ids.ids):
                        del values['company_id']
                uid = 1 # safe fields only, so we write as super-user to bypass access rights

        res = super(ResUsers, self).write(cr, uid, ids, values, context=context)
        if 'company_id' in values:
            for user in self.browse(cr, uid, ids, context=context):
                # if partner is global we keep it that way
                if user.partner_id.company_id and user.partner_id.company_id.id != values['company_id']:
                    user.partner_id.write({'company_id': user.company_id.id})
            # clear default ir values when company changes
            self.pool['ir.values'].get_defaults_dict.clear_cache(self.pool['ir.values'])
        # clear caches linked to the users
        self.pool['ir.model.access'].call_cache_clearing_methods(cr)
        clear = partial(self.pool['ir.rule'].clear_cache, cr)
        map(clear, ids)
        db = cr.dbname
        if db in self._uid_cache:
            for id in ids:
                if id in self._uid_cache[db]:
                    del self._uid_cache[db][id]
        self.context_get.clear_cache(self)
        self.has_group_wrapper.clear_cache(self)
        return res

    @api.multi
    def unlink(self):
        if 1 in self.ids:
            raise UserError(_('You can not remove the admin user as it is used internally for resources created by Odoo (updates, module installation, ...)'))
        db = self.env.cr.dbname
        if db in self._uid_cache:
            for id in self.ids:
                if id in self._uid_cache[db]:
                    del self._uid_cache[db][id]
        return super(ResUsers, self).unlink()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args=[]
        users = []
        if name and operator in ['=', 'ilike']:
            users = self.search([('login', '=', name)] + args, limit=limit)
        if not users:
            users = self.search([('name', operator, name)] + args, limit=limit)
        return users.name_get()

    @api.one
    def copy(self, default=None):
        user2copy = self.read(['login', 'name'])[0]
        default = dict(default or {})
        if ('name' not in default) and ('partner_id' not in default):
            default['name'] = _("%s (copy)") % user2copy['name']
        if 'login' not in default:
            default['login'] = _("%s (copy)") % user2copy['login']
        return super(ResUsers, self).copy(default)

    @tools.ormcache()
    def context_get(self):
        result = {}
        for k in self._fields:
            if k.startswith('context_'):
                context_key = k[8:]
            elif k in ['lang', 'tz']:
                context_key = k
            else:
                context_key = False
            if context_key:
                res = getattr(self.env.user, k) or False
                if isinstance(res, models.BaseModel):
                    res = res.id
                result[context_key] = res or False
        return result

    @api.model
    def action_get(self):
        IrModelData = self.env['ir.model.data']
        data_id = IrModelData.sudo()._get_id('base', 'action_res_users_my')
        return IrModelData.browse(data_id).res_id

    def check_super(self, passwd):
        if passwd == tools.config['admin_passwd']:
            return True
        else:
            raise openerp.exceptions.AccessDenied()

    def check_credentials(self, uid, password):
        """ Override this method to plug additional authentication methods"""
        res = self.sudo().search([('id', '=', uid), ('password', '=', password)])
        if not res:
            raise openerp.exceptions.AccessDenied()

    def _login(self, db, login, password):
        if not password:
            return False
        user_id = False
        try:
            # autocommit: our single update request will be performed atomically.
            # (In this way, there is no opportunity to have two transactions
            # interleaving their cr.execute()..cr.commit() calls and have one
            # of them rolled back due to a concurrent access.)
            self.env.cr.autocommit(True)
            # check if user exists
            res = self.sudo().search([('login', '=', login)])
            if res:
                user_id = res[0]
                # check credentials
                self.check_credentials(user_id, password)
                # We effectively unconditionally write the res_users line.
                # Even w/ autocommit there's a chance the user row will be locked,
                # in which case we can't delay the login just for the purpose of
                # update the last login date - hence we use FOR UPDATE NOWAIT to
                # try to get the lock - fail-fast
                # Failing to acquire the lock on the res_users row probably means
                # another request is holding it. No big deal, we don't want to
                # prevent/delay login in that case. It will also have been logged
                # as a SQL error, if anyone cares.
                try:
                    # NO KEY introduced in PostgreSQL 9.3 http://www.postgresql.org/docs/9.3/static/release-9-3.html#AEN115299
                    update_clause = 'NO KEY UPDATE' if self.env.cr._cnx.server_version >= 90300 else 'UPDATE'
                    self.env.cr.execute("SELECT id FROM ResUsers WHERE id=%%s FOR %s NOWAIT" % update_clause, (user_id,), log_exceptions=False)
                    self.env.cr.execute("UPDATE ResUsers SET login_date = now() AT TIME ZONE 'UTC' WHERE id=%s", (user_id,))
                    self.invalidate_cache(['login_date'], [user_id])
                except Exception:
                    _logger.debug(
                        "Failed to update last_login for db:%s login:%s", db, login, exc_info=True)
        except openerp.exceptions.AccessDenied:
            _logger.info("Login failed for db:%s login:%s", db, login)
            user_id = False
        finally:
            self.env.cr.close()

        return user_id

    def authenticate(self, db, login, password, user_agent_env):
        """Verifies and returns the user ID corresponding to the given
          ``login`` and ``password`` combination, or False if there was
          no matching user.

           :param str db: the database on which user is trying to authenticate
           :param str login: username
           :param str password: user password
           :param dict user_agent_env: environment dictionary describing any
               relevant environment attributes
        """
        uid = self._login(db, login, password)
        if uid == SUPERUSER_ID:
            # Successfully logged in as admin!
            # Attempt to guess the web base url...
            if user_agent_env and user_agent_env.get('base_location'):
                cr = self.env.cursor()
                try:
                    base = user_agent_env['base_location']
                    ICP = self.env['ir.config_parameter']
                    if not ICP.get_param(cr, uid, 'web.base.url.freeze'):
                        ICP.set_param(cr, uid, 'web.base.url', base)
                    cr.commit()
                except Exception:
                    _logger.exception("Failed to update web.base.url configuration parameter")
                finally:
                    cr.close()
        return uid

    def check(self, db, uid, passwd):
        """Verifies that the given (uid, password) is authorized for the database ``db`` and
           raise an exception if it is not."""
        if not passwd:
            # empty passwords disallowed for obvious security reasons
            raise openerp.exceptions.AccessDenied()
        if self._uid_cache.get(db, {}).get(uid) == passwd:
            return
        cr = self.env.cursor()
        try:
            self.check_credentials(cr, uid, passwd)
            if self._uid_cache.has_key(db):
                self._uid_cache[db][uid] = passwd
            else:
                self._uid_cache[db] = {uid:passwd}
        finally:
            cr.close()

    def change_password(self, old_passwd, new_passwd):
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.

        :return: True
        :raise: openerp.exceptions.AccessDenied when old password is wrong
        :raise: except_osv when new password is not set or empty
        """
        self.check(self.env.cr.dbname, self.env.user.id, old_passwd)
        if new_passwd:
            return self.write({'password': new_passwd})
        raise UserError(_("Setting empty passwords is not allowed for security reasons!"))

    @api.multi
    def preference_save(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'reload_context',
        }

    @api.multi
    def preference_change_password(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'change_password',
            'target': 'new',
        }

    @tools.ormcache()
    def has_group_wrapper(self, group_ext_id):
            return self.has_group(self.env.uid, self.group_ext_id)

    @tools.ormcache('uid', 'group_ext_id')
    def has_group(self, cr, uid, group_ext_id):
        """Checks whether user belongs to given group.

        :param str group_ext_id: external ID (XML ID) of the group.
           Must be provided in fully-qualified form (``module.ext_id``), as there
           is no implicit module to use..
        :return: True if the current user is a member of the group with the
           given external ID (XML ID), else False.
        """
        assert group_ext_id and '.' in group_ext_id, "External ID must be fully qualified"
        module, ext_id = group_ext_id.split('.')
        cr.execute("""SELECT 1 FROM res_groups_users_rel WHERE uid=%s AND gid IN
                        (SELECT res_id FROM ir_model_data WHERE module=%s AND name=%s)""",
                   (uid, module, ext_id))
        return bool(cr.fetchone())

    def get_company_currency_id(self):
        return self.company_id.currency_id.id

#----------------------------------------------------------
# Implied groups
#
# Extension of res.groups and res.users with a relation for "implied"
# or "inherited" groups.  Once a user belongs to a group, it
# automatically belongs to the implied groups (transitively).
#----------------------------------------------------------


class cset(object):
    """ A cset (constrained set) is a set of elements that may be constrained to
        be a subset of other csets.  Elements added to a cset are automatically
        added to its supersets.  Cycles in the subset constraints are supported.
    """
    def __init__(self, xs):
        self.supersets = set()
        self.elements = set(xs)

    def subsetof(self, other):
        if other is not self:
            self.supersets.add(other)
            other.update(self.elements)

    def update(self, xs):
        xs = set(xs) - self.elements
        if xs:      # xs will eventually be empty in case of a cycle
            self.elements.update(xs)
            for s in self.supersets:
                s.update(xs)

    def __iter__(self):
        return iter(self.elements)

concat = itertools.chain.from_iterable


class GroupsImplied(models.Model):
    _inherit = 'res.groups'

    @api.multi
    def _get_trans_implied(self):
        "computes the transitive closure of relation implied_ids"
        memo = {}           # use a memo for performance and cycle avoidance

        def computed_set(g):
            if g not in memo:
                memo[g] = cset(g.implied_ids)
                for h in g.implied_ids:
                    computed_set(h).subsetof(memo[g])
            return memo[g]

        res = {}
        for g in self.sudo():
            res[g.id] = map(int, computed_set(g))
        return res

    implied_ids = fields.Many2many('res.groups', 'res_groups_implied_rel', 'gid', 'hid',
                                   string='Inherits',
                                   help='Users of this group automatically inherit those groups')
    trans_implied_ids = fields.Many2many('res.groups', compute='_get_trans_implied',
                                         string='Transitively inherits')

    @api.model
    def create(self, values):
        users = values.pop('users', None)
        groups = super(GroupsImplied, self).create(values)
        if users:
            # delegate addition of users to add implied groups
            groups.write({'users': users})
        return groups

    @api.multi
    def write(self, values):
        res = super(GroupsImplied, self).write(values)
        if values.get('users') or values.get('implied_ids'):
            # add all implied groups (to all users of each group)
            for group in self:
                gids = map(int, group.trans_implied_ids)
                vals = {'users': [(4, u.id) for u in group.users]}
                super(GroupsImplied, self.browse(gids)).write(vals)
        return res


class UsersImplied(models.Model):
    _inherit = 'res.users'

    @api.model
    def create(self, values):
        groups = values.pop('groups_id', None)
        user = super(UsersImplied, self).create(values)
        if groups:
            # delegate addition of groups to add implied groups
            user.write({'groups_id': groups})
            self.env['ir.ui.view'].clear_cache()
        return user

    @api.multi
    def write(self, values):
        res = super(UsersImplied, self).write(values)
        if values.get('groups_id'):
            # add implied groups for all users
            for user in self:
                gs = set(concat(g.trans_implied_ids for g in user.groups_id))
                vals = {'groups_id': [(4, g.id) for g in gs]}
                super(UsersImplied, user).write(vals)
            self.env['ir.ui.view'].clear_cache()
        return res

#----------------------------------------------------------
# Vitrual checkbox and selection for res.user form view
#
# Extension of res.groups and res.users for the special groups view in the users
# form.  This extension presents groups with selection and boolean widgets:
# - Groups are shown by application, with boolean and/or selection fields.
#   Selection fields typically defines a role "Name" for the given application.
# - Uncategorized groups are presented as boolean fields and grouped in a
#   section "Others".
#
# The user form view is modified by an inherited view (base.user_groups_view);
# the inherited view replaces the field 'groups_id' by a set of reified group
# fields (boolean or selection fields).  The arch of that view is regenerated
# each time groups are changed.
#
# Naming conventions for reified groups fields:
# - boolean field 'in_group_ID' is True iff
#       ID is in 'groups_id'
# - selection field 'sel_groups_ID1_..._IDk' is ID iff
#       ID is in 'groups_id' and ID is maximal in the set {ID1, ..., IDk}
#----------------------------------------------------------


def name_boolean_group(id):
    return 'in_group_' + str(id)


def name_selection_groups(ids):
    return 'sel_groups_' + '_'.join(map(str, ids))


def is_boolean_group(name):
    return name.startswith('in_group_')


def is_selection_groups(name):
    return name.startswith('sel_groups_')


def is_reified_group(name):
    return is_boolean_group(name) or is_selection_groups(name)


def get_boolean_group(name):
    return int(name[9:])


def get_selection_groups(name):
    return map(int, name[11:].split('_'))


def partition(f, xs):
    "return a pair equivalent to (filter(f, xs), filter(lambda x: not f(x), xs))"
    yes, nos = [], []
    for x in xs:
        (yes if f(x) else nos).append(x)
    return yes, nos


def parse_m2m(commands):
    "return a list of ids corresponding to a many2many value"
    ids = []
    for command in commands:
        if isinstance(command, (tuple, list)):
            if command[0] in (1, 4):
                ids.append(command[2])
            elif command[0] == 5:
                ids = []
            elif command[0] == 6:
                ids = list(command[2])
        else:
            ids.append(command)
    return ids


class GroupsView(models.Model):
    _inherit = 'res.groups'

    @api.model
    def create(self, values):
        res = super(GroupsView, self).create(values)
        self.update_user_groups_view()
        # ir_values.get_actions() depends on action records
        self.env['ir.values'].clear_caches()
        return res

    @api.multi
    def write(self, values):
        res = super(GroupsView, self).write(values)
        self.update_user_groups_view()
        # ir_values.get_actions() depends on action records
        self.env['ir.values'].clear_caches()
        return res

    @api.multi
    def unlink(self):
        res = super(GroupsView, self).unlink()
        self.update_user_groups_view()
        # ir_values.get_actions() depends on action records
        self.env['ir.values'].clear_caches()
        return res

    def update_user_groups_view(self):
        # the view with id 'base.user_groups_view' inherits the user form view,
        # and introduces the reified group fields
        # we have to try-catch this, because at first init the view does not exist
        # but we are already creating some basic groups
        if not self.env.context or self.env.context.get('install_mode'):
            # use installation/admin language for translatable names in the view
            context = dict(self.env.context or {})
            context.update(self.env['res.users'].context_get())

        view = self.env['ir.model.data'].sudo().with_context(
            self.env.context).xmlid_to_object('base.user_groups_view')
        if view and view.exists() and view._name == 'ir.ui.view':
            xml1, xml2 = [], []
            xml1.append(E.separator(string=_('Application'), colspan="2"))
            for app, kind, gs in self.with_context(self.env.context).get_groups_by_application():
                # hide groups in category 'Hidden' (except to group_no_one)
                attrs = {'groups': 'base.group_no_one'} if app and app.xml_id == 'base.module_category_hidden' else {}
                if kind == 'selection':
                    # application name with a selection field
                    field_name = name_selection_groups(map(int, gs))
                    xml1.append(E.field(name=field_name, **attrs))
                    xml1.append(E.newline())
                else:
                    # application separator with boolean fields
                    app_name = app and app.name or _('Other')
                    xml2.append(E.separator(string=app_name, colspan="4", **attrs))
                    for g in gs:
                        field_name = name_boolean_group(g.id)
                        xml2.append(E.field(name=field_name, **attrs))

            xml2.append({'class': "o_label_nowrap"})
            xml = E.field(E.group(*(xml1), col="2"), E.group(*(xml2), col="4"), name="groups_id", position="replace")
            xml.addprevious(etree.Comment("GENERATED AUTOMATICALLY BY GROUPS"))
            xml_content = etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="utf-8")
            view.write({'arch': xml_content})
        return True

    def get_application_groups(self, domain=None):
        if domain is None:
            domain = []
        domain.append(('share', '=', False))
        return self.search(domain)

    def get_groups_by_application(self):
        """ return all groups classified by application (module category), as a list of pairs:
                [(app, kind, [group, ...]), ...],
            where app and group are browse records, and kind is either 'boolean' or 'selection'.
            Applications are given in sequence order.  If kind is 'selection', the groups are
            given in reverse implication order.
        """
        def linearized(gs):
            gs = set(gs)
            # determine sequence order: a group should appear after its implied groups
            order = dict.fromkeys(gs, 0)
            for g in gs:
                for h in gs.intersection(g.trans_implied_ids):
                    order[h] -= 1
            # check whether order is total, i.e., sequence orders are distinct
            if len(set(order.itervalues())) == len(gs):
                return sorted(gs, key=lambda g: order[g])
            return None

        # classify all groups by application
        gids = self.get_application_groups()
        by_app, others = {}, []
        for g in gids:
            if g.category_id:
                by_app.setdefault(g.category_id, []).append(g)
            else:
                others.append(g)
        # build the result
        res = []
        apps = sorted(by_app.iterkeys(), key=lambda a: a.sequence or 0)
        for app in apps:
            gs = linearized(by_app[app])
            if gs:
                res.append((app, 'selection', gs))
            else:
                res.append((app, 'boolean', by_app[app]))
        if others:
            res.append((False, 'boolean', others))
        return res


class UsersView(models.Model):
    _inherit = 'res.users'

    @api.model
    def create(self, values):
        values = self._remove_reified_groups(values)
        return super(UsersView, self).create(values)

    @api.multi
    def write(self, values):
        values = self._remove_reified_groups(values)
        return super(UsersView, self).write(values)

    def _remove_reified_groups(self, values):
        """ return `values` without reified group fields """
        add, rem = [], []
        values1 = {}

        for key, val in values.iteritems():
            if is_boolean_group(key):
                (add if val else rem).append(get_boolean_group(key))
            elif is_selection_groups(key):
                rem += get_selection_groups(key)
                if val:
                    add.append(val)
            else:
                values1[key] = val

        if 'groups_id' not in values and (add or rem):
            # remove group ids in `rem` and add group ids in `add`
            values1['groups_id'] = zip(repeat(3), rem) + zip(repeat(4), add)

        return values1

    @api.model
    def default_get(self, fields):
        group_fields, fields = partition(is_reified_group, fields)
        fields1 = (fields + ['groups_id']) if group_fields else fields
        values = super(UsersView, self).default_get(fields1)
        self._add_reified_groups(group_fields, values)

        # add "default_groups_ref" inside the context to set default value for group_id with xml values
        if 'groups_id' in fields and isinstance(self.env.context.get("default_groups_ref"), list):
            groups = []
            for group_xml_id in self.env.context["default_groups_ref"]:
                group_split = group_xml_id.split('.')
                if len(group_split) != 2:
                    raise UserError(_('Invalid context default_groups_ref value (model.name_id) : "%s"') % group_xml_id)
                try:
                    print '---group_split--->', group_split
                    temp, group_id = self.env.ref(group_split[0], group_split[1])
                except ValueError:
                    group_id = False
                groups += [group_id]
            values['groups_id'] = groups
        return values

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        # determine whether reified groups fields are required, and which ones
        fields1 = fields or self.fields_get().keys()
        group_fields, other_fields = partition(is_reified_group, fields1)

        # read regular fields (other_fields); add 'groups_id' if necessary
        drop_groups_id = False
        if group_fields and fields:
            if 'groups_id' not in other_fields:
                other_fields.append('groups_id')
                drop_groups_id = True
        else:
            other_fields = fields

        res = super(UsersView, self).read(other_fields, load=load)

        # post-process result to add reified group fields
        if group_fields:
            for values in (res if isinstance(res, list) else [res]):
                self._add_reified_groups(group_fields, values)
                if drop_groups_id:
                    values.pop('groups_id', None)
        return res

    def _add_reified_groups(self, fields, values):
        """ add the given reified group fields into `values` """
        gids = set(parse_m2m(values.get('groups_id') or []))
        for f in fields:
            if is_boolean_group(f):
                values[f] = get_boolean_group(f) in gids
            elif is_selection_groups(f):
                selected = [gid for gid in get_selection_groups(f) if gid in gids]
                values[f] = selected and selected[-1] or False

    @api.model
    def fields_get(self, allfields=None, write_access=True, attributes=None):
        res = super(UsersView, self).fields_get(allfields=allfields,
                                                write_access=write_access,
                                                attributes=attributes)
        # add reified groups fields
        if self.env.uid != SUPERUSER_ID and not self.has_group_wrapper('base.group_erp_manager'):
            return res
        for app, kind, gs in self.env['res.groups'].get_groups_by_application():
            if kind == 'selection':
                # selection group field
                tips = ['%s: %s' % (g.name, g.comment) for g in gs if g.comment]
                res[name_selection_groups(map(int, gs))] = {
                    'type': 'selection',
                    'string': app and app.name or _('Other'),
                    'selection': [(False, '')] + [(g.id, g.name) for g in gs],
                    'help': '\n'.join(tips),
                    'exportable': False,
                    'selectable': False,
                }
            else:
                # boolean group fields
                for g in gs:
                    res[name_boolean_group(g.id)] = {
                        'type': 'boolean',
                        'string': g.name,
                        'help': g.comment,
                        'exportable': False,
                        'selectable': False,
                    }
        return res

#----------------------------------------------------------
# change password wizard
#----------------------------------------------------------


class ChangePasswordWizard(models.TransientModel):
    """
        A wizard to manage the change of users' passwords
    """

    _name = "change.password.wizard"
    _description = "Change Password Wizard"

    @api.multi
    def _default_user_ids(self):
        user_model = self.env['res.users']
        user_ids = self.env.context.get('active_model') == 'res.users' and self.env.context.get('active_ids') or []
        print '--user_ids-->', user_ids
        return [
            (0, 0, {'user_id': user.id, 'user_login': user.login})
            for user in user_model.browse(user_ids)
        ]

    user_ids = fields.One2many('change.password.user', 'wizard_id', string='Users',
                               default=_default_user_ids)

    @api.multi
    def change_password_button(self):
        # wizard = self.browse()[0]
        need_reload = any(self.env.user.id == user.user_id.id for user in self.user_ids)

        line_ids = [user.id for user in self.user_ids]
        self.env['change.password.user'].change_password_button(line_ids)

        if need_reload:
            return {
                'type': 'ir.actions.client',
                'tag': 'reload'
            }

        return {'type': 'ir.actions.act_window_close'}


class ChangePasswordUser(models.TransientModel):
    """
        A model to configure users in the change password wizard
    """

    _name = 'change.password.user'
    _description = 'Change Password Wizard User'

    wizard_id = fields.Many2one('change.password.wizard', string='Wizard', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    user_login = fields.Char(readonly=True)
    new_passwd = fields.Char(string='New Password', default='')

    def change_password_button(self):
        for line in self:
            line.user_id.write({'password': line.new_passwd})
        # don't keep temporary passwords in the database longer than necessary
        self.write({'new_passwd': False})
