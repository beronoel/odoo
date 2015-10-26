# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import itertools
from itertools import repeat
from lxml import etree
from lxml.builder import E
import logging

import odoo
from odoo import api, fields, models, SUPERUSER_ID, tools, _
import odoo.exceptions
from odoo.osv import expression
from odoo.service.db import check_super
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Only users who can modify the user (incl. the user herself) see the real contents of these fields
USER_PRIVATE_FIELDS = ['password']

#----------------------------------------------------------
# Basic res.groups and res.users
#----------------------------------------------------------

class ResGroups(models.Model):
    _name = "res.groups"
    _description = "Access Groups"
    _rec_name = 'display_name'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    users = fields.Many2many('res.users', 'res_groups_users_rel', 'gid', 'uid')
    model_access = fields.One2many('ir.model.access', 'group_id', 'Access Controls', copy=True)
    rule_groups = fields.Many2many('ir.rule', 'rule_group_rel', 'group_id', 'rule_group_id', string='Rules', domain=[('global', '=', False)])
    menu_access = fields.Many2many('ir.ui.menu', 'ir_ui_menu_group_rel', 'gid', 'menu_id', 'Access Menu')
    view_access = fields.Many2many('ir.ui.view', 'ir_ui_view_group_rel', 'group_id', 'view_id', 'Views')
    comment = fields.Text(translate=True)
    category_id = fields.Many2one('ir.module.category', 'Application', index=True)
    color = fields.Integer('Color Index')
    display_name = fields.Char(compute='_get_full_name', string='Group Name', search='_search_group')
    share = fields.Boolean('Share Group', help="Group created to set access rights for sharing data with some users.")

    _sql_constraints = [
        ('name_uniq', 'unique (category_id, name)', 'The name of the group must be unique within an application!')
    ]

    @api.multi
    @api.depends('name', 'category_id')
    def name_get(self):
        result = []
        for g in self.sudo():
            if g.category_id:
                cal_name = '%s / %s' % (g.category_id.name, g.name)
            else:
                cal_name = g.name
            result += [(g.id, cal_name)]
        return result

    def _get_full_name(self):
        super(ResGroups, self).sudo()._compute_display_name()

    def _search_group(self, operator, vals):
        operand = vals
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
            category_domain = [('category_id.name', operator, lst and [category_name] or category_name)]
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

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # add explicit ordering if search is sorted on full_name
        if order and order.startswith('display_name'):
            gs = super(ResGroups, self).search(args)
            gs.sort(key=lambda g: g.display_name, reverse=order.endswith('DESC'))
            gs = gs[offset:offset+limit] if limit else gs[offset:]
            return map(int, gs)
        return super(ResGroups, self).search(args=args, offset=offset, limit=limit, order=order, count=count)

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        group_name = self.read(['name'])[0]['name']
        default.update({'name': _('%s (copy)') % group_name})
        return super(ResGroups, self).copy(default)

    @api.multi
    def write(self, vals):
        if 'name' in vals:
            if vals['name'].startswith('-'):
                raise UserError(_('The name of the group can not start with "-"'))
        res = super(ResGroups, self).write(vals)
        # self.env['ir.model.access'].call_cache_clearing_methods()
        self.sudo().invalidate_cache()
        self.env['res.users'].has_group.clear_cache(self.env['res.users'])
        return res

class ResUsersLog(models.Model):
    _name = 'res.users.log'
    _order = 'id desc'
    # Currenly only uses the magical fields: create_uid, create_date,
    # for recording logins. To be extended for other uses (chat presence, etc.)


class ResUsers(models.Model):
    """ User class. A res.users record models an odoo user and is different
        from an employee.
        res.users class now inherits from res.partner. The partner model is
        used to store the data related to the partner: lang, name, address,
        avatar, ... The user model is now dedicated to technical data.
    """
    __uid_cache = {}
    _inherits = {
        'res.partner': 'partner_id',
    }
    _name = "res.users"
    _description = 'Users'
    _order = 'name, login'

    @api.multi
    def _set_new_password(self, value, args):
        self.ensure_one()
        if value is False:
            # Do not update the password if no value is provided, ignore silently.
            # For example web client submits False values for all empty fields.
            return
        if self.env.uid == self.id:
            # To change their own password users must use the client-specific change password wizard,
            # so that the new password is immediately used for further RPC requests, otherwise the user
            # will face unexpected 'Access Denied' exceptions.
            raise UserError(_('Please use the change password wizard (in User Preferences or User menu) to change your own password.'))
        self.write({'password': value})

    def _get_password(self):
        return dict.fromkeys(self.ids, '')

    @api.depends('groups_id')
    def _is_share(self):
        for user in self:
            user.share = not self.sudo(user.id).has_group('base.group_user')

    @api.multi
    @api.depends('share')
    def _get_users_from_group(self):
        result = set()
        groups = self.env['res.groups'].browse(self.ids)
        # Clear cache to avoid perf degradation on databases with thousands of users
        groups.invalidate_cache()
        for group in groups:
            result.update(user.id for user in group.users)
        return list(result)

    #Default methods
    def _get_companies(self):
        company = self._get_company()
        if company:
            return company.ids
        return False

    @api.v8
    def _get_company(self, uid2=False):
        if not uid2:
            uid2 = self.env.user
        return uid2.company_id or uid2.company_id.id

    @api.v7
    def _get_company(self, cr, uid, context=None, uid2=False):
        if not uid2:
            uid2 = uid
        # Use read() to compute default company, and pass load=_classic_write to
        # avoid useless name_get() calls. This will avoid prefetching fields
        # while computing default values for new db columns, as the
        # db backend may not be fully initialized yet.
        user_data = self.pool['res.users'].read(cr, uid, uid2, ['company_id'],
                                                context=context, load='_classic_write')[0]
        comp_id = user_data['company_id']
        return comp_id or False

    def _get_group(self):
        default_user = self.env['ir.model.data'].xmlid_to_object('base.default_user')
        if not default_user:
            return []
        result = default_user.groups_id.ids
        return result

    id = fields.Integer(string="ID")
    partner_id = fields.Many2one('res.partner', required=True, string='Related Partner', ondelete='restrict', help='Partner-related data of the user', auto_join=True)
    login = fields.Char(required=True, help="Used to log into the system")
    password = fields.Char(invisible=True, copy=False, help="Keep empty if you don't want the user to be able to connect on the system.", default='')
    new_password = fields.Char(compute='_get_password', inverse='_set_new_password', string='Set Password', help="Specify a value only when creating a user or if you're " \
            "changing the user's password, otherwise leave empty. After "\
            "a change of password, the user has to login again.")
    signature = fields.Html()
    active = fields.Boolean(default=True)
    action_id = fields.Many2one('ir.actions.actions', string='Home Action', help="If specified, this action will be opened at log on for this user, in addition to the standard menu.")
    groups_id = fields.Many2many('res.groups', 'res_groups_users_rel', 'uid', 'gid', string='Groups', default=_get_group)
    # # Special behavior for this field: res.company.search() will only return the companies
    # # available to the current user (should be the user's companies?), when the user_preference
    # # context is set.
    company_id = fields.Many2one('res.company', string='Company', required=True, help='The company this user is currently working for.', context={'user_preference': True}, default=_get_company)
    company_ids = fields.Many2many('res.company', 'res_company_users_rel', 'user_id', 'cid', string='Companies', default=_get_companies)
    # overridden inherited fields to bypass access rights, in case you have
    # access to the user but not its corresponding partner
    name = fields.Char(related='partner_id.name', inherited=True)
    email = fields.Char(related='partner_id.email', inherited=True)
    log_ids = fields.One2many('res.users.log', 'create_uid', string='User log entries')
    login_date = fields.Datetime(related='log_ids.create_date', string='Latest connection')
    #customer = fields.Boolean(string='Is a Customer', default=False, help="Check this box if this contact is a customer.")
    share = fields.Boolean(compute='_is_share', string='Share User', store=True, help="External user with limited access, created only for the purpose of sharing data.")

    _default = {
        'customer': False
    }

    @api.multi
    @api.onchange('login')
    def on_change_login(self):
        if self.login and tools.single_email_re.match(self.login):
            self.email = self.login

    @api.multi
    @api.onchange('state_id')
    def onchange_state(self, state_id):
        partner_ids = [user.partner_id.id for user in self]
        return self.env['res.partner'].browse(partner_ids).onchange_state(state_id)

    @api.multi
    def onchange_parent_id(self, parent_id):
        """ Wrapper on the user.partner onchange_address, because some calls to the
            partner form view applied to the user may trigger the
            partner.onchange_type method, but applied to the user object.
        """
        partner_ids = [user.partner_id.id for user in self]
        return self.env['res.partner'].browse(partner_ids).onchange_address(parent_id)

    @api.multi
    @api.constrains('company_id', 'company_ids')
    def _check_company(self):
        if not all(((this.company_id in this.company_ids) or not this.company_ids) for this in self):
            raise ValueError(_('The chosen company is not in the allowed companies for this user'))

    _sql_constraints = [
        ('login_key', 'UNIQUE (login)',  'You can not have two users with the same login !')
    ]


    # User can write on a few of his own fields (but not his groups for example)
    SELF_WRITEABLE_FIELDS = ['password', 'signature', 'action_id', 'company_id', 'email', 'name', 'image', 'image_medium', 'image_small', 'lang', 'tz']
    # User can read a few of his own fields
    SELF_READABLE_FIELDS = ['signature', 'company_id', 'login', 'email', 'name', 'image', 'image_medium', 'image_small', 'lang', 'tz', 'tz_offset', 'groups_id', 'partner_id', '__last_update', 'action_id']

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        def override_password(o):
            if ('id' not in o or o['id'] != self.env.uid):
                for f in USER_PRIVATE_FIELDS:
                    if f in o:
                        o[f] = '********'
            return o
        uid = self.env.uid
        if fields and (self.ids == [self.env.uid] or self.ids == self.env.uid):
            for key in fields:
                if not (key in self.SELF_READABLE_FIELDS or key.startswith('context_')):
                    break
            else:
                # safe fields only, so we read as super-user to bypass access rights
                uid = SUPERUSER_ID
        result = super(ResUsers, self).read(fields=fields, load=load)
        canwrite = self.env['ir.model.access'].sudo(uid).check('res.users', 'write', False)
        if not canwrite:
            if isinstance(self.ids, (int, long)):
                result = override_password(result)
            else:
                result = map(override_password, result)

        return result


    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if self.env.uid != SUPERUSER_ID:
            groupby_fields = set([groupby] if isinstance(groupby, basestring) else groupby)
            if groupby_fields.intersection(USER_PRIVATE_FIELDS):
                raise odoo.exceptions.AccessError('Invalid groupby')
        return super(ResUsers, self).read_group(domain=domain, fields=fields, groupby=groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if self.env.user.id != SUPERUSER_ID and args:
            domain_terms = [term for term in args if isinstance(term, (tuple, list))]
            domain_fields = set(left for (left, op, right) in domain_terms)
            if domain_fields.intersection(USER_PRIVATE_FIELDS):
                raise odoo.exceptions.AccessError('Invalid search criterion')
        return super(ResUsers, self)._search(args, offset=offset, limit=limit, order=order, count=count, access_rights_uid=access_rights_uid)

    @api.model
    def create(self, vals):
        user = super(ResUsers, self).create(vals)
        if user.partner_id.company_id:
            user.partner_id.write({'company_id': user.company_id.id})
        return user

    @api.multi
    def write(self, values):
        if not hasattr(self.ids, '__iter__'):
            self.ids = [self.ids]

        if values.get('active') == False:
            for current_id in self.ids:
                if current_id == SUPERUSER_ID:
                    raise UserError(_("You cannot deactivate the admin user."))
                elif current_id == self.env.uid:
                    raise UserError(_("You cannot deactivate the user you're currently logged in as."))
        if self.ids == [self.env.uid]:
            for key in values.keys():
                if not (key in self.SELF_WRITEABLE_FIELDS or key.startswith('context_')):
                    break
            else:
                if 'company_id' in values:
                    user = self.sudo()
                    if not (values['company_id'] in user.company_ids.ids):
                        del values['company_id']
                self.env.uid = SUPERUSER_ID  # safe fields only, so we write as super-user to bypass access rights

        res = super(ResUsers, self).write(values)
        if 'company_id' in values:
            for user in self:
                # if partner is global we keep it that way
                if user.partner_id.company_id and user.partner_id.company_id.id != values['company_id']:
                    user.partner_id.write({'company_id': user.company_id.id})
            # clear default ir values when company changes
            self.env['ir.values'].get_defaults_dict.clear_cache(self.env['ir.values'])
        # clear caches linked to the users
        self.env['ir.model.access'].call_cache_clearing_methods()
        self.clear_caches()
        db = self.env.cr.dbname
        if db in self.__uid_cache:
            for id in self.ids:
                if id in self.__uid_cache[db]:
                    del self.__uid_cache[db][id]
        self.context_get.clear_cache(self)
        self.has_group.clear_cache(self)
        return res

    @api.multi
    def unlink(self):
        if 1 in self.ids:
            raise UserError(_('You can not remove the admin user as it is used internally for resources created by Odoo (updates, module installation, ...)'))
        db = self.env.cr.dbname
        if db in self.__uid_cache:
            for id in self.ids:
                if id in self.__uid_cache[db]:
                    del self.__uid_cache[db][id]
        return super(ResUsers, self).unlink()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        ids = []
        if name and operator in ['=', 'ilike']:
            rec = self.search([('login', '=', name)] + args, limit=limit)
        if not ids:
            rec = self.search([('name', operator, name)] + args, limit=limit)
        return rec.name_get()

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        user2copy = self.read(['login', 'name'])[0]
        default = dict(default or {})
        if ('name' not in default) and ('partner_id' not in default):
            default['name'] = _("%s (copy)") % user2copy['name']
        if 'login' not in default:
            default['login'] = _("%s (copy)") % user2copy['login']
        return super(ResUsers, self).copy(default)

    @api.model
    @tools.ormcache('self.env.uid')
    def context_get(self):
        user = self.sudo()
        result = {}
        for k in self._fields:
            if k.startswith('context_'):
                context_key = k[8:]
            elif k in ['lang', 'tz']:
                context_key = k
            else:
                context_key = False
            if context_key:
                res = getattr(user, k) or False
                if isinstance(res, models.BaseModel):
                    res = res.id
                result[context_key] = res or False
        return result

    @api.model
    def action_get(self):
        ModelData = self.env['ir.model.data']
        data_id = ModelData.sudo()._get_id('base', 'action_res_users_my')
        return ModelData.browse(data_id).res_id

    def check_super(self, passwd):
        return check_super(passwd)

    @api.model
    def check_credentials(self, password):
        """ Override this method to plug additional authentication methods"""
        res = self.sudo().search([('id', '=', self.env.uid), ('password', '=', password)])
        if not res:
            raise odoo.exceptions.AccessDenied()

    def _update_last_login(self, cr, uid):
        # only create new records to avoid any side-effect on concurrent transactions
        # extra records will be deleted by the periodical garbage collection
        self.pool['res.users.log'].create(cr, uid, {})  # populated by defaults

    def _login(self, db, login, password):
        if not password:
            return False
        user_id = False
        try:
            with self.pool.cursor() as cr:
                res = self.search(cr, SUPERUSER_ID, [('login', '=', login)])
                if res:
                    user_id = res[0]
                    self.check_credentials(cr, user_id, password)
                    self._update_last_login(cr, user_id)
        except odoo.exceptions.AccessDenied:
            _logger.info("Login failed for db:%s login:%s", db, login)
            user_id = False
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
                cr = self.pool.cursor()
                try:
                    base = user_agent_env['base_location']
                    ICP = self.pool['ir.config_parameter']
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
            raise odoo.exceptions.AccessDenied()
        if self.__uid_cache.setdefault(db, {}).get(uid) == passwd:
            return
        cr = self.pool.cursor()
        try:
            self.check_credentials(cr, uid, passwd)
            self.__uid_cache[db][uid] = passwd
        finally:
            cr.close()

    @api.model
    def change_password(self, old_passwd, new_passwd):
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.
        :return: True
        :raise: odoo.exceptions.AccessDenied when old password is wrong
        :raise: except_osv when new password is not set or empty
        """
        self.check(self.env.cr.dbname, self.env.uid, old_passwd)
        if new_passwd:
            return self.env.user.write({'password': new_passwd})
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

    @api.model
    @tools.ormcache('self.env.uid', 'group_ext_id')
    def has_group(self, group_ext_id):
        """Checks whether user belongs to given group.
        :param str group_ext_id: external ID (XML ID) of the group.
           Must be provided in fully-qualified form (``module.ext_id``), as there
           is no implicit module to use..
        :return: True if the current user is a member of the group with the
           given external ID (XML ID), else False.
        """
        assert group_ext_id and '.' in group_ext_id, "External ID must be fully qualified"
        module, ext_id = group_ext_id.split('.')
        self.env.cr.execute("""SELECT 1 FROM res_groups_users_rel WHERE uid=%s AND gid IN
                        (SELECT res_id FROM ir_model_data WHERE module=%s AND name=%s)""", (self.env.uid, module, ext_id))
        return bool(self.env.cr.fetchone())

    @api.multi
    def _is_admin(self):
        return self.id == odoo.SUPERUSER_ID or self.sudo(self).has_group('base.group_erp_manager')

    @api.model
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

    def _get_trans_implied(self):
        "computes the transitive closure of relation implied_ids"
        memo = {}           # use a memo for performance and cycle avoidance
        def computed_set(g):
            if g not in memo:
                memo[g] = cset(g.implied_ids)
                for h in g.implied_ids:
                    computed_set(h).subsetof(memo[g])
            return memo[g]

        for g in self:
            g.trans_implied_ids = map(int, computed_set(g))

    implied_ids = fields.Many2many('res.groups', 'res_groups_implied_rel', 'gid', 'hid',
        string='Inherits', help='Users of this group automatically inherit those groups')
    trans_implied_ids = fields.Many2many('res.groups', compute='_get_trans_implied', string='Transitively inherits')


    @api.model
    def create(self, values):
        users = values.pop('users', None)
        gid = super(GroupsImplied, self).create(values)
        if users:
            # delegate addition of users to add implied groups
            gid.write({'users': users})
        return gid

    @api.multi
    def write(self, values):
        res = super(GroupsImplied, self).write(values)
        if values.get('users') or values.get('implied_ids'):
            # add all implied groups (to all users of each group)
            for g in self:
                gids = map(int, g.trans_implied_ids)
                vals = {'users': [(4, u.id) for u in g.users]}
                super(GroupsImplied, self.browse(gids)).write(vals)
        return res

class UsersImplied(models.Model):
    _inherit = 'res.users'

    @api.model
    def create(self, values):
        groups = values.pop('groups_id', None)
        records = super(UsersImplied, self).create(values)
        if groups:
            # delegate addition of groups to add implied groups
            records.write({'groups_id': groups})
            self.env['ir.ui.view'].clear_cache()
        return records

    @api.multi
    def write(self, values):
        if not isinstance(self.ids, list):
            self.ids = [self.ids]
        res = super(UsersImplied, self).write(values)
        if values.get('groups_id'):
            # add implied groups for all users
            for user in self:
                gs = set(concat(g.trans_implied_ids for g in user.groups_id))
                vals = {'groups_id': [(4, g.id) for g in gs]}
                super(UsersImplied, user).write(vals)
            self.pool['ir.ui.view'].clear_cache()
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
                ids.append(command[1])
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
        user_context = dict(self.env.context or {})
        if user_context.get('install_mode'):
            # use installation/admin language for translatable names in the view
            user_context.update(self.env['res.users'].context_get())
        view = self.env['ir.model.data'].sudo().with_context(user_context).xmlid_to_object('base.user_groups_view')
        if view and view.exists() and view._name == 'ir.ui.view':
            group_no_one = view.env.ref('base.group_no_one')
            xml1, xml2 = [], []
            xml1.append(E.separator(string=_('Application'), colspan="2"))
            for app, kind, gs in self.with_context(user_context).get_groups_by_application():
                # hide groups in category 'Hidden' (except to group_no_one)
                attrs = {'groups': 'base.group_no_one'} if app and (app.xml_id == 'base.module_category_hidden' or app.xml_id == 'base.module_category_extra') else {}
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
                        if g == group_no_one:
                            # make the group_no_one invisible in the form view
                            xml2.append(E.field(name=field_name, invisible="1", **attrs))
                        else:
                            xml2.append(E.field(name=field_name, **attrs))

            xml2.append({'class': "o_label_nowrap"})
            xml = E.field(E.group(*(xml1), col="2"), E.group(*(xml2), col="4"), name="groups_id", position="replace")
            xml.addprevious(etree.Comment("GENERATED AUTOMATICALLY BY GROUPS"))
            xml_content = etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="utf-8")
            view.with_context(self.env.context, lang=None).write({'arch': xml_content})
        return True

    @api.model
    def get_application_groups(self, domain=None):
        if domain is None:
            domain = []
        domain.append(('share', '=', False))
        return [rec.id for rec in self.search(domain)]

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
        for g in self.browse(gids):
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

        res = super(UsersView, self).read(fields=other_fields, load=load)

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
        res = super(UsersView, self).fields_get(allfields=allfields, write_access=write_access, attributes=attributes)
        # add reified groups fields
        if not self.env['res.users'].browse([self.env.uid])._is_admin():
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

    def _default_user_ids(self):
        ResUsers = self.env['res.users']
        user_ids = self.env.context.get('active_model') == 'res.users' and self.env.context.get('active_ids') or []
        return [
            (0, 0, {'user_id': user.id, 'user_login': user.login})
            for user in ResUsers.browse(user_ids)
        ]

    user_ids = fields.One2many('change.password.user', 'wizard_id', string='Users', default=_default_user_ids)

    @api.multi
    def change_password_button(self):
        wizard = self[0]
        need_reload = any(self.env.uid == user.user_id.id for user in wizard.user_ids)

        line_ids = [user.id for user in wizard.user_ids]
        self.env['change.password.user'].browse(line_ids).change_password_button()

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
    user_login = fields.Char('User Login', readonly=True)
    new_passwd = fields.Char(string='New Password', default='')

    def change_password_button(self):
        for line in self:
            line.user_id.write({'password': line.new_passwd})
        # don't keep temporary passwords in the database longer than necessary
        self.write({'new_passwd': False})
