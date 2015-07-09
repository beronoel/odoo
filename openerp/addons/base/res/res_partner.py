# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime
from lxml import etree
import pytz
import urlparse

import openerp
from openerp import api, fields, models, tools, _
from openerp.osv import osv
from openerp.osv.expression import get_unaccent_wrapper
from openerp.exceptions import UserError

ADDRESS_FORMAT_LAYOUTS = {
    '%(city)s %(state_code)s\n%(zip)s': """
        <div class="address_format">
            <field name="city" placeholder="%(city)s" style="width: 50%%"/>
            <field name="state_id" class="oe_no_button" placeholder="%(state)s" style="width: 47%%" options='{"no_open": true}'/>
            <br/>
            <field name="zip" placeholder="%(zip)s"/>
        </div>
    """,
    '%(zip)s %(city)s': """
        <div class="address_format">
            <field name="zip" placeholder="%(zip)s" style="width: 40%%"/>
            <field name="city" placeholder="%(city)s" style="width: 57%%"/>
            <br/>
            <field name="state_id" class="oe_no_button" placeholder="%(state)s" options='{"no_open": true}'/>
        </div>
    """,
    '%(city)s\n%(state_name)s\n%(zip)s': """
        <div class="address_format">
            <field name="city" placeholder="%(city)s"/>
            <field name="state_id" class="oe_no_button" placeholder="%(state)s" options='{"no_open": true}'/>
            <field name="zip" placeholder="%(zip)s"/>
        </div>
    """
}


class format_address(object):
    @api.model
    def fields_view_get_address(self, arch):
        fmt = self.env.user.company_id.country_id.address_format or ''
        for k, v in ADDRESS_FORMAT_LAYOUTS.items():
            if k in fmt:
                doc = etree.fromstring(arch)
                for node in doc.xpath("//div[@class='address_format']"):
                    tree = etree.fromstring(v % {
                        'city': _('City'), 'zip': _('ZIP'), 'state': _('State')})
                    for child in node.xpath("//field"):
                        if child.attrib.get('modifiers'):
                            for field in tree.xpath("//field[@name='%s']" % child.attrib.get('name')):
                                field.attrib['modifiers'] = child.attrib.get('modifiers')
                    node.getparent().replace(node, tree)
                arch = etree.tostring(doc)
                break
        return arch


@api.model
def _tz_get(self):
    # put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
    return [(tz,tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]


class ResPartnerCategory(models.Model):

    def name_get(self):
        """ Return the categories' display name, including their direct
            parent by default.

            If ``context['partner_category_display']`` is ``'short'``, the short
            version of the category name (without the direct parent) is used.
            The default is the long version.
        """

        if self.env.context.get('partner_category_display') == 'short':
            return super(ResPartnerCategory, self).name_get()

        res = []
        for category in self:
            names = []
            current = category
            while current:
                names.append(current.name)
                current = current.parent_id
            res.append((category.id, ' / '.join(reversed(names))))
        return res

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            # Be sure name_search is symetric to name_get
            name = name.split(' / ')[-1]
            args = [('name', operator, name)] + args
        categories = self.search(args, limit=limit)
        return categories.name_get()

    @api.multi
    def _name_get_fnc(self, field_name, arg):
        return dict(self.name_get())

    _description = 'Partner Categories'
    _name = 'res.partner.category'

    name = fields.Char(string='Category Name', required=True, translate=True)
    parent_id = fields.Many2one('res.partner.category', string='Parent Category',
                                index=True, ondelete='cascade')
    complete_name = fields.Char(string='Full Name', compute='_name_get_fnc')
    child_ids = fields.One2many('res.partner.category', 'parent_id', string='Child Categories')
    active = fields.Boolean(
        default=True,
        help="The active field allows you to hide the category without removing it.")
    parent_left = fields.Integer(string='Left parent', index=True)
    parent_right = fields.Integer(string='Right parent', index=True)
    partner_ids = fields.Many2many('res.partner', 'category_id', 'partner_id', string='Partners')

    _constraints = [
        (osv.osv._check_recursion,
         'Error ! You can not create recursive categories.', ['parent_id'])
    ]

    _parent_store = True
    _parent_order = 'name'
    _order = 'parent_left'


class ResPartnerTitle(models.Model):
    _name = 'res.partner.title'
    _order = 'name'

    name = fields.Char(string='Title', required=True, translate=True)
    shortcut = fields.Char(string='Abbreviation', translate=True)
    domain = fields.Selection([('partner', 'Partner'), ('contact', 'Contact')],
                              required=True, default='contact')


@api.model
def _lang_get(self):
    languages = self.env['res.lang'].search([])
    return [(language.code, language.name) for language in languages]

# fields copy if 'use_parent_address' is checked
ADDRESS_FIELDS = ('street', 'street2', 'zip', 'city', 'state_id', 'country_id')


class ResPartner(models.Model, format_address):
    _description = 'Partner'
    _name = "res.partner"

    @api.multi
    def _address_display(self):
        res = {}
        for partner in self:
            res[partner.id] = self._display_address(partner)
        return res

    @api.multi
    def _get_tz_offset(self):
        return dict(
            (p.id, datetime.datetime.now(pytz.timezone(p.tz or 'GMT')).strftime('%z'))
            for p in self)

    @api.depends('image')
    def _get_image(self):
        return dict((p.id, tools.image_get_resized_images(p.image)) for p in self)

    def _set_image(self):
        self.image = tools.image_resize_image_big(self.image)

    @api.depends('parent_id', 'is_company')
    def _commercial_partner_compute(self):
        """ Returns the partner that is considered the commercial
        entity of this partner. The commercial entity holds the master data
        for all commercial fields (see :py:meth:`~_commercial_fields`) """
        for partner in self:
            current_partner = partner
            while not current_partner.is_company and current_partner.parent_id:
                current_partner = current_partner.parent_id
            self.partner_id = current_partner

    @api.depends('parent_id', 'is_company', 'name')
    def _display_name_compute(self):
        context = dict(self.env.context or {})
        context.pop('show_address', None)
        context.pop('show_address_only', None)
        context.pop('show_email', None)
        return dict(self.name_get())

    def _default_category(self):
        category_id = self.env.context.get('category_id', False)
        return [category_id] if category_id else False

    def _default_company(self):
        return self.env.user.company_id

    _order = "display_name"

    name = fields.Char(required=True, index=True)
    display_name = fields.Char(compute='_display_name_compute', string='Name',
                               store=True, index=True)
    date = fields.Date(index=True)
    title = fields.Many2one('res.partner.title')
    parent_id = fields.Many2one('res.partner', string='Related Company', index=True)
    parent_name = fields.Char(related='parent_id.name', readonly=True, string='Parent name')
    child_ids = fields.One2many('res.partner', 'parent_id', string='Contacts',
                                domain=[('active', '=', True)])  # force "active_test" domain to bypass _search() override
    ref = fields.Char(string='Internal Reference', index=True)
    lang = fields.Selection(_lang_get, string='Language',
                            default=lambda self: self.env.lang,
                            help="If the selected language is loaded in the system, all documents related to this contact will be printed in this language. If not, it will be English.")
    tz = fields.Selection(_tz_get, string='Timezone',
                          default=lambda self: self.env.context.get('tz', False),
                          help="The partner's timezone, used to output proper date and time values inside printed reports. "
                               "It is important to set a value for this field. You should use the same timezone "
                               "that is otherwise used to pick and render date and time values: your computer's timezone.")
    tz_offset = fields.Char(compute='_get_tz_offset', string='Timezone offset', invisible=True)
    user_id = fields.Many2one(
        'res.users', string='Salesperson',
        help='The internal user that is in charge of communicating with this contact if any.')
    vat = fields.Char(string='TIN',
                      help="Tax Identification Number. Fill it if the company is subjected to taxes. Used by the some of the legal statements.")
    bank_ids = fields.One2many('res.partner.bank', 'partner_id', string='Banks')
    website = fields.Char(help="Website of Partner or Company")
    comment = fields.Text(string='Notes')
    category_id = fields.Many2many('res.partner.category', 'partner_id', 'category_id',
                                   string='Categories', default=_default_category)
    credit_limit = fields.Float()
    barcode = fields.Char(oldname='ean13')
    active = fields.Boolean(default=True)
    customer = fields.Boolean(string='Is a Customer',
                              default=True,
                              help="Check this box if this contact is a customer.")
    supplier = fields.Boolean(string='Is a Supplier',
                              help="Check this box if this contact is a supplier. If it's not checked, purchase people will not see it when encoding a purchase order.")
    employee = fields.Boolean(help="Check this box if this contact is an Employee.")
    function = fields.Char(string='Job Position')
    type = fields.Selection([('default', 'Default'), ('invoice', 'Invoice'),
                             ('delivery', 'Shipping'), ('contact', 'Contact'),
                             ('other', 'Other')], string='Address Type',
                            default='contact',
                            help="Used to select automatically the right address according to the context in sales and purchases documents.")
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char(change_default=True)
    city = fields.Char()
    state_id = fields.Many2one("res.country.state", string='State', ondelete='restrict')
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict')
    email = fields.Char()
    phone = fields.Char()
    fax = fields.Char()
    mobile = fields.Char()
    birthdate = fields.Char()
    is_company = fields.Boolean(string='Is a Company', default=False, store=True,
                                help="Check if the contact is a company, otherwise it is a person")
    use_parent_address = fields.Boolean(
        string='Use Company Address', default=False,
        help="Select this if you want to set company's address information  for this contact")
    # image: all image fields are base64 encoded and PIL-supported
    image = fields.Binary(
        default=False,
        help="This field holds the image used as avatar for this contact, limited to 1024x1024px")
    image_medium = fields.Binary(compute='_get_image', inverse='_set_image',
                                 string="Medium-sized image", store=True,
                                 help="Medium-sized image of this contact. It is automatically "\
                                      "resized as a 128x128px image, with aspect ratio preserved. "\
                                      "Use this field in form views or some kanban views.")
    image_small = fields.Binary(compute='_get_image', inverse='_set_image',
                                string="Small-sized image", store=True,
                                help="Small-sized image of this contact. It is automatically "\
                                     "resized as a 64x64px image, with aspect ratio preserved. "\
                                     "Use this field anywhere a small image is required.")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=_default_company, index=True)
    color = fields.Integer(string='Color Index', default=0)
    user_ids = fields.One2many('res.users', 'partner_id', string='Users')
    contact_address = fields.Char(compute='_address_display', string='Complete Address')

    # technical field used for managing commercial fields
    commercial_partner_id = fields.Many2one('res.partner',
                                            string='Commercial Entity',
                                            compute='_commercial_partner_compute',
                                            store=True)

    @api.model
    def _get_default_image(self, is_company, colorize=False):
        img_path = openerp.modules.get_module_resource(
            'base', 'static/src/img', 'company_image.png' if is_company else 'avatar.png')
        with open(img_path, 'rb') as f:
            image = f.read()

        # colorize user avatars
        if not is_company:
            image = tools.image_colorize(image)

        return tools.image_resize_image_big(image.encode('base64'))

    @api.model
    def fields_view_get(self, view_id=None, view_type='form',
                        toolbar=False, submenu=False):
        if (not view_id) and (view_type == 'form') and self.env.context and self.env.context.get('force_email', False):
            view_id = self.env.ref('base.view_partner_simple_form').id
        res = super(ResPartner, self).fields_view_get(view_id=view_id, view_type=view_type,
                                                      toolbar=toolbar, submenu=submenu)
        if view_type == 'form':
            res['arch'] = self.fields_view_get_address(res['arch'])
        return res

    _constraints = [
        (osv.osv._check_recursion,
         'You cannot create recursive Partner hierarchies.', ['parent_id']),
    ]

    @api.one
    def copy(self, default=None):
        default = dict(default or {})
        default['name'] = _('%s (copy)') % self.name
        return super(ResPartner, self).copy(default)

    @api.onchange('is_company')
    def onchange_type(self):
        self.title = False
        if self.is_company:
            self.use_parent_address = False
            domain = {'title': [('domain', '=', 'partner')]}
        else:
            domain = {'title': [('domain', '=', 'contact')]}
        return {'domain': domain}

    @api.multi
    @api.onchange('use_parent_address', 'parent_id')
    def onchange_address(self, use_parent_address, parent_id):
        def value_or_id(val):
            """ return val or val.id if val is a browse record """
            return val if isinstance(val, (bool, int, long, float, basestring)) else val.id
        result = {}
        if parent_id:
            if self.ids:
                if self.parent_id and self.parent_id.id != parent_id:
                    result['warning'] = {'title': _('Warning'),
                                         'message': _('Changing the company of a contact should only be done if it '
                                                      'was never correctly set. If an existing contact starts working for a new '
                                                      'company then a new contact should be created under that new '
                                                      'company. You can use the "Discard" button to abandon this change.')}
            if use_parent_address and self.parent_id:
                self.street = self.partner_id['street']
                self.street2 = self.partner_id['street2']
                self.zip = self.partner_id['zip']
                self.city = self.partner_id['city']
                self.state_id = self.partner_id['state_id']
                self.country_id = self.partner_id['country_id']

        else:
            self.use_parent_address = False
        return result

    @api.onchange('state_id')
    def onchange_state(self):
        if self.state_id:
            state = self.env['res.country.state'].browse(self.state_id)
            self.country_id = state.country_id.id

    @api.model
    def _update_fields_values(self, partner, fields):
        """ Returns dict of write() values for synchronizing ``fields`` """
        values = {}
        for fname in fields:
            field = self._fields[fname]
            if field.type == 'one2many':
                raise AssertionError('One2Many fields cannot be synchronized as part of `commercial_fields` or `address fields`')
            if field.type == 'many2one':
                values[fname] = partner[fname].id if partner[fname] else False
            elif field.type == 'many2many':
                values[fname] = [(6,0,[r.id for r in partner[fname] or []])]
            else:
                values[fname] = partner[fname]
        return values

    @api.multi
    def _address_fields(self):
        """ Returns the list of address fields that are synced from the parent
        when the `use_parent_address` flag is set. """
        return list(ADDRESS_FIELDS)

    @api.multi
    def update_address(self, vals):
        address_fields = self._address_fields()
        addr_vals = dict((key, vals[key]) for key in address_fields if key in vals)
        if addr_vals:
            return super(ResPartner, self).write(addr_vals)

    @api.multi
    def _commercial_fields(self):
        """ Returns the list of fields that are managed by the commercial entity
        to which a partner belongs. These fields are meant to be hidden on
        partners that aren't `commercial entities` themselves, and will be
        delegated to the parent `commercial entity`. The list is meant to be
        extended by inheriting classes. """
        return ['vat', 'credit_limit']

    @api.multi
    def _commercial_sync_from_company(self):
        """ Handle sync of commercial fields when a new parent commercial entity is set,
        as if they were related fields """
        commercial_partner = self.commercial_partner_id
        if not commercial_partner:
            # On child partner creation of a parent partner,
            # the commercial_partner_id is not yet computed
            commercial_partner_id = self._commercial_partner_compute()
            commercial_partner = self.browse(commercial_partner_id)
        if commercial_partner != self:
            commercial_fields = self._commercial_fields()
            sync_vals = self._update_fields_values(commercial_partner, commercial_fields)
            self.write(sync_vals)

    @api.multi
    def _commercial_sync_to_children(self):
        """ Handle sync of commercial fields to descendants """
        commercial_fields = self._commercial_fields()
        commercial_partner = self.commercial_partner_id
        if not commercial_partner:
            # On child partner creation of a parent partner,
            # the commercial_partner_id is not yet computed
            commercial_partner_id = self._commercial_partner_compute()
            commercial_partner = self.browse(commercial_partner_id)
        sync_vals = self._update_fields_values(commercial_partner,
                                               commercial_fields)
        sync_children = [c for c in self.child_ids if not c.is_company]
        for child in sync_children:
            self._commercial_sync_to_children(child)
        for child in sync_children:
            child.write(sync_vals)

    @api.model
    def _fields_sync(self, partner, update_values):
        """ Sync commercial fields and address fields from company and to children after create/update,
        just as if those were all modeled as fields.related to the parent """
        # 1. From UPSTREAM: sync from parent
        if update_values.get('parent_id') or update_values.get('use_parent_address'):
            # 1a. Commercial fields: sync if parent changed
            if update_values.get('parent_id'):
                partner._commercial_sync_from_company()
            # 1b. Address fields: sync if parent or use_parent changed *and* both are now set
            if partner.id and partner.use_parent_address:
                onchange_vals = partner.onchange_address(
                    use_parent_address=partner.use_parent_address,
                    parent_id=partner.id).get('value', {})
                partner.update_address(onchange_vals)

        # 2. To DOWNSTREAM: sync children
        if partner.child_ids:
            # 2a. Commercial Fields: sync if commercial entity
            if partner.commercial_partner_id == partner:
                commercial_fields = self._commercial_fields()
                if any(field in update_values for field in commercial_fields):
                    partner._commercial_sync_to_children()
            # 2b. Address fields: sync if address changed
            address_fields = self._address_fields()
            if any(field in update_values for field in address_fields):
                update_ids = partner.search([('parent_id', '=', partner.id),
                                             ('use_parent_address', '=', True)])
                update_ids.update_address(update_values)

    @api.multi
    def _handle_first_contact_creation(self, partner):
        """ On creation of first contact for a company (or root) that has no address, assume contact address
        was meant to be company address """
        parent = partner.parent_id
        address_fields = self._address_fields()
        if parent and (parent.is_company or not parent.parent_id) and len(parent.child_ids) == 1 and \
           any(partner[f] for f in address_fields) and not any(parent[f] for f in address_fields):
            addr_vals = self._update_fields_values(partner, address_fields)
            parent.update_address(addr_vals)
            if not parent.is_company:
                parent.write({'is_company': True})

    @api.multi
    def unlink(self):
        orphan_contact = self.search([('parent_id', 'in', self.ids),
                                      ('id', 'not in', self.ids),
                                      ('use_parent_address', '=', True)])
        if orphan_contact:
            # no longer have a parent address
            orphan_contact.write({'use_parent_address': False})
        return super(ResPartner, self).unlink()

    def _clean_website(self, website):
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(website)
        if not scheme:
            if not netloc:
                netloc, path = path, ''
            website = urlparse.urlunparse(('http', netloc, path, params, query, fragment))
        return website

    @api.multi
    def write(self, vals):
        # res.partner must only allow to set the company_id of a partner if it
        # is the same as the company of all users that inherit from this partner
        # (this is to allow the code from res_users to write to the partner!) or
        # if setting the company_id to False (this is compatible with any user
        # company)
        if vals.get('website'):
            vals['website'] = self._clean_website(vals['website'])
        if vals.get('company_id'):
            company = self.env['res.company'].browse(vals['company_id'])
            for partner in self:
                if partner.user_ids:
                    companies = set(user.company_id for user in partner.user_ids)
                    if len(companies) > 1 or company not in companies:
                        raise UserError(_("You can not change the company as the partner/user has multiple user linked with different companies."))

        result = super(ResPartner, self).write(vals)
        for partner in self:
            self._fields_sync(partner, vals)
        return result

    @api.model
    def create(self, vals):
        if vals.get('website'):
            vals['website'] = self._clean_website(vals['website'])
        partner = super(ResPartner, self).create(vals)
        self._fields_sync(partner, vals)
        self._handle_first_contact_creation(partner)
        return partner

    @api.multi
    def open_commercial_entity(self):
        """ Utility method used to add an "Open Company" button in partner views """
        return {'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'view_mode': 'form',
                'res_id': self.commercial_partner_id.id,
                'target': 'current',
                'flags': {'form': {'action_buttons': True}}}

    @api.multi
    def open_parent(self):
        """ Utility method used to add an "Open Parent" button in partner views """
        return {'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'view_mode': 'form',
                'res_id': self.parent_id.id,
                'target': 'new',
                'flags': {'form': {'action_buttons': True}}}

    @api.multi
    def name_get(self):
        res = []
        for record in self:
            name = record.name
            if record.parent_id and not record.is_company:
                name = "%s, %s" % (record.parent_name, name)
            if self.env.context.get('show_address_only'):
                name = self._display_address(record, without_company=True)
            if self.env.context.get('show_address'):
                name = name + "\n" + self._display_address(record, without_company=True)
            name = name.replace('\n\n', '\n')
            if self.env.context.get('show_email') and record.email:
                name = "%s <%s>" % (name, record.email)
            res.append((record.id, name))
        return res

    def _parse_partner_name(self, text):
        """ Supported syntax:
            - 'Raoul <raoul@grosbedon.fr>': will find name and email address
            - otherwise: default, everything is set as the name """
        emails = tools.email_split(text.replace(' ', ','))
        if emails:
            email = emails[0]
            name = text[:text.index(email)].replace('"', '').replace('<', '').strip()
        else:
            name, email = text, ''
        return name, email

    def name_create(self, name):
        """ Override of orm's name_create method for partners. The purpose is
            to handle some basic formats to create partners using the
            name_create.
            If only an email address is received and that the regex cannot find
            a name, the name will have the email value.
            If 'force_email' key in context: must find the email address. """
        name, email = self._parse_partner_name(name)
        if self.env.context.get('force_email') and not email:
            raise UserError(_("Couldn't create contact without email address!"))
        if not name and email:
            name = email
        record = self.create({self._rec_name: name or email, 'email': email or False})
        return record.name_get()

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        """ Override search() to always show inactive children when searching via ``child_of`` operator. The ORM will
        always call search() with a simple domain of the form [('parent_id', 'in', [ids])]. """
        # a special ``domain`` is set on the ``child_ids`` o2m to bypass this logic, as it uses similar domain expressions
        active = {}
        if len(args) == 1 and len(args[0]) == 3 and args[0][:2] == ('parent_id', 'in') \
                and args[0][2] != [False]:
            active['active_test'] = False
        return super(ResPartner, self.with_context(active))._search(
            args, offset=offset, limit=limit, order=order, count=count,
            access_rights_uid=access_rights_uid)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []
        if name and operator in ('=', 'ilike', '=ilike', 'like', '=like'):

            self.check_access_rights('read')
            where_query = self._where_calc(args)
            self._apply_ir_rules(where_query, 'read')
            from_clause, where_clause, where_clause_params = where_query.get_sql()
            where_str = where_clause and (" WHERE %s AND " % where_clause) or ' WHERE '

            # search on the name of the contacts and of its company
            search_name = name
            if operator in ('ilike', 'like'):
                search_name = '%%%s%%' % name
            if operator in ('=ilike', '=like'):
                operator = operator[1:]

            unaccent = get_unaccent_wrapper(self.env.cr)

            query = """SELECT id
                         FROM ResPartner
                      {where} ({email} {operator} {percent}
                           OR {display_name} {operator} {percent}
                           OR {reference} {operator} {percent})
                           -- don't panic, trust postgres bitmap
                     ORDER BY {display_name} {operator} {percent} desc,
                              {display_name}
                    """.format(where=where_str,
                               operator=operator,
                               email=unaccent('email'),
                               display_name=unaccent('display_name'),
                               reference=unaccent('ref'),
                               percent=unaccent('%s'))

            where_clause_params += [search_name]*4
            if limit:
                query += ' limit %s'
                where_clause_params.append(limit)
            self.env.cr.execute(query, where_clause_params)
            ids = map(lambda x: x[0], self.env.cr.fetchall())

            if ids:
                return self.name_get()
            else:
                return []
        return super(ResPartner, self).name_search(name, args, operator=operator,
                                                   limit=limit)

    @api.multi
    def find_or_create(self, email):
        """ Find a partner with the given ``email`` or use :py:method:`~.name_create`
            to create one

            :param str email: email-like string, which should contain at least one email,
                e.g. ``"Raoul Grosbedon <r.g@grosbedon.fr>"``"""
        assert email, 'an email is required for find_or_create to work'
        emails = tools.email_split(email)
        if emails:
            email = emails[0]
        records = self.search([('email', '=ilike', email)])
        if not records:
            return self.name_create(email)[0]
        return records[0]

    def _email_send(self, email_from, subject, body, on_error=None):
        for partner in self:
            if partner.email:
                tools.email_send(email_from, [partner.email], subject, body, on_error)
        return True

    @api.multi
    def email_send(self, email_from, subject, body, on_error=''):
        while len(self.ids):
            self.env['ir.cron'].create({
                'name': 'Send Partner Emails',
                'user_id': self.env.user.id,
                'model': 'res.partner',
                'function': '_email_send',
                'args': repr([self.ids[:16], email_from, subject, body, on_error])
            })
            self.ids = self.ids[16:]
        return True

    @api.multi
    def address_get(self, adr_pref=None):
        """ Find contacts/addresses of the right type(s) by doing a depth-first-search
        through descendants within company boundaries (stop at entities flagged ``is_company``)
        then continuing the search at the ancestors that are within the same company boundaries.
        Defaults to partners of type ``'default'`` when the exact type is not found, or to the
        provided partner itself if no type ``'default'`` is found either. """
        adr_pref = set(adr_pref or [])
        if 'default' not in adr_pref:
            adr_pref.add('default')
        result = {}
        visited = set()
        for partner in self:
            current_partner = partner
            while current_partner:
                to_scan = [current_partner]
                # Scan descendants, DFS
                while to_scan:
                    record = to_scan.pop(0)
                    visited.add(record)
                    if record.type in adr_pref and not result.get(record.type):
                        result[record.type] = record.id
                    if len(result) == len(adr_pref):
                        return result
                    to_scan = [c for c in record.child_ids
                               if c not in visited
                               if not c.is_company] + to_scan

                # Continue scanning at ancestor if current_partner is not a commercial entity
                if current_partner.is_company or not current_partner.parent_id:
                    break
                current_partner = current_partner.parent_id

        # default to type 'default' or the partner itself
        default = result.get('default', ids and ids[0] or False)
        for adr_type in adr_pref:
            result[adr_type] = result.get(adr_type) or default
        return result

    @api.multi
    def view_header_get(self, view_id, view_type):
        res = super(ResPartner, self).view_header_get(view_id, view_type)
        if res:
            return res
        if not self.env.context.get('category_id', False):
            return False
        return _('Partners: ')+self.env['res.partner.category'].browse(
            self.env.context.get('category_id')).name

    @api.model
    @api.returns('self')
    def main_partner(self):
        ''' Return the main partner '''
        return self.env.ref('base.main_partner')

    def _display_address(self, address, without_company=False):
        '''
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.

        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        '''

        # get the information that will be injected into the display format
        # get the address format
        address_format = address.country_id.address_format or \
            "%(street)s\n%(street2)s\n%(city)s %(state_code)s %(zip)s\n%(country_name)s"
        args = {
            'state_code': address.state_id.code or '',
            'state_name': address.state_id.name or '',
            'country_code': address.country_id.code or '',
            'country_name': address.country_id.name or '',
            'company_name': address.parent_name or '',
        }
        for field in self._address_fields():
            args[field] = getattr(address, field) or ''
        if without_company:
            args['company_name'] = ''
        elif address.parent_id:
            address_format = '%(company_name)s\n' + address_format
        return address_format % args
