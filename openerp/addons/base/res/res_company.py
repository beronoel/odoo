# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import os
import re
from openerp import api, fields, models, tools, _
from openerp.osv import osv
from openerp.tools import image_resize_image


class ResCompany(models.Model):
    _name = "res.company"
    _description = 'Companies'
    _order = 'name'

    @api.multi
    def _get_address_data(self):
        for company in self:
            if company.partner_id:
                address_data = company.partner_id.sudo().address_get(adr_pref=['default'])
                if address_data['default']:
                    company.street = company.partner_id.street
                    company.street2 = company.partner_id.street2
                    company.city = company.partner_id.city
                    company.zip = company.partner_id.zip
                    company.state_id = company.partner_id.state_id.id
                    company.country_id = company.partner_id.country_id.id
                    company.fax = company.partner_id.fax

    def _set_address_data_street(self):
        self.partner_id.street = self.street

    def _set_address_data_street2(self):
        self.partner_id.street2 = self.street2

    def _set_address_data_zip(self):
        self.partner_id.zip = self.zip

    def _set_address_data_city(self):
        self.partner_id.city = self.city

    def _set_address_data_state(self):
        self.partner_id.state_id = self.state_id.id

    def _set_address_data_country(self):
        self.partner_id.country_id = self.country_id.id

    def _set_address_data_fax(self):
        self.partner_id.fax = self.fax

    @api.depends('partner_id', 'partner_id.image')
    def _get_logo_web(self):
        result = {}
        for record in self:
            size = (180, None)
            result[record.id] = image_resize_image(record.partner_id.image, size)
        return result

    def _get_euro(self):
        rate = self.env['res.currency.rate'].search([('rate', '=', 1)])
        return rate and rate.id

    def _get_logo(self):
        return open(os.path.join( tools.config['root_path'], 'addons', 'base', 'res', 'res_company_logo.png'), 'rb') .read().encode('base64')

    def _get_font(self):
        res = self.env['res.font'].search(
            [('family', '=', 'Helvetica'), ('mode', '=', 'all')], limit=1)
        return res and res.id

    _header = """
<header>
<pageTemplate>
    <frame id="first" x1="28.0" y1="28.0" width="%s" height="%s"/>
    <stylesheet>
       <!-- Set here the default font to use for all <para> tags -->
       <paraStyle name='Normal' fontName="DejaVuSans"/>
    </stylesheet>
    <pageGraphics>
        <fill color="black"/>
        <stroke color="black"/>
        <setFont name="DejaVuSans" size="8"/>
        <drawString x="%s" y="%s"> [[ formatLang(time.strftime("%%Y-%%m-%%d"), date=True) ]]  [[ time.strftime("%%H:%%M") ]]</drawString>
        <setFont name="DejaVuSans-Bold" size="10"/>
        <drawCentredString x="%s" y="%s">[[ company.partner_id.name ]]</drawCentredString>
        <stroke color="#000000"/>
        <lines>%s</lines>
        <!-- Set here the default font to use for all <drawString> tags -->
        <!-- don't forget to change the 2 other occurence of <setFont> above if needed -->
        <setFont name="DejaVuSans" size="8"/>
    </pageGraphics>
</pageTemplate>
</header>"""

    _header2 = _header % (539, 772, "1.0cm", "28.3cm", "11.1cm", "28.3cm", "1.0cm 28.1cm 20.1cm 28.1cm")

    _header3 = _header % (786, 525, 25, 555, 440, 555, "25 550 818 550")

    def _get_header(self):
        try:
            header_file = tools.file_open(os.path.join(
                'base', 'report', 'corporate_rml_header.rml'))
            try:
                return header_file.read()
            finally:
                header_file.close()
        except:
            return self._header_a4

    _header_main = """
<header>
    <pageTemplate>
        <frame id="first" x1="1.3cm" y1="3.0cm" height="%s" width="19.0cm"/>
         <stylesheet>
            <!-- Set here the default font to use for all <para> tags -->
            <paraStyle name='Normal' fontName="DejaVuSans"/>
            <paraStyle name="main_footer" fontSize="8.0" alignment="CENTER"/>
            <paraStyle name="main_header" fontSize="8.0" leading="10" alignment="LEFT" spaceBefore="0.0" spaceAfter="0.0"/>
         </stylesheet>
        <pageGraphics>
            <!-- Set here the default font to use for all <drawString> tags -->
            <setFont name="DejaVuSans" size="8"/>
            <!-- You Logo - Change X,Y,Width and Height -->
            <image x="1.3cm" y="%s" height="40.0" >[[ company.logo or removeParentNode('image') ]]</image>
            <fill color="black"/>
            <stroke color="black"/>

            <!-- page header -->
            <lines>1.3cm %s 20cm %s</lines>
            <drawRightString x="20cm" y="%s">[[ company.rml_header1 ]]</drawRightString>
            <drawString x="1.3cm" y="%s">[[ company.partner_id.name ]]</drawString>
            <place x="1.3cm" y="%s" height="1.8cm" width="15.0cm">
                <para style="main_header">[[ display_address(company.partner_id) or  '' ]]</para>
            </place>
            <drawString x="1.3cm" y="%s">Phone:</drawString>
            <drawRightString x="7cm" y="%s">[[ company.partner_id.phone or '' ]]</drawRightString>
            <drawString x="1.3cm" y="%s">Mail:</drawString>
            <drawRightString x="7cm" y="%s">[[ company.partner_id.email or '' ]]</drawRightString>
            <lines>1.3cm %s 7cm %s</lines>

            <!-- left margin -->
            <rotate degrees="90"/>
            <fill color="grey"/>
            <drawString x="2.65cm" y="-0.4cm">generated by Odoo.com</drawString>
            <fill color="black"/>
            <rotate degrees="-90"/>

            <!--page bottom-->
            <lines>1.2cm 2.65cm 19.9cm 2.65cm</lines>
            <place x="1.3cm" y="0cm" height="2.55cm" width="19.0cm">
                <para style="main_footer">[[ company.rml_footer ]]</para>
                <para style="main_footer">Contact : [[ user.name ]] - Page: <pageNumber/></para>
            </place>
        </pageGraphics>
    </pageTemplate>
</header>"""

    _header_a4 = _header_main % ('21.7cm', '27.7cm', '27.7cm', '27.7cm', '27.8cm', '27.3cm', '25.3cm', '25.0cm', '25.0cm', '24.6cm', '24.6cm', '24.5cm', '24.5cm')
    _header_letter = _header_main % ('20cm', '26.0cm', '26.0cm', '26.0cm', '26.1cm', '25.6cm', '23.6cm', '23.3cm', '23.3cm', '22.9cm', '22.9cm', '22.8cm', '22.8cm')

    @api.onchange('rml_paper_format')
    def onchange_rml_paper_format(self):
        if self.rml_paper_format == 'us_letter':
            self.rml_header = self._header_letter
        self.rml_header = self._header_a4

    @api.one
    def act_discover_fonts(self):
        return self.env['res.font'].font_scan()

    @api.onchange('custom_footer', 'phone', 'fax', 'email', 'website', 'vat',
                  'company_registry', 'bank_ids')
    def onchange_footer(self):
        if self.custom_footer:
            return {}

        # first line (notice that missing elements are filtered out before the join)
        res = ' | '.join(filter(bool, [
            self.phone and '%s: %s' % (_('Phone'), self.phone),
            self.fax and '%s: %s' % (_('Fax'), self.fax),
            self.email and '%s: %s' % (_('Email'), self.email),
            self.website and '%s: %s' % (_('Website'), self.website),
            self.vat and '%s: %s' % (_('TIN'), self.vat),
            self.company_registry and '%s: %s' % (_('Reg'), self.company_registry),
        ]))
        # second line: bank accounts
        account_data = self.resolve_2many_commands('bank_ids', self.bank_ids)
        account_names = self.env['res.partner.bank']._prepare_name_get(account_data)
        if account_names:
            title = _('Bank Accounts') if len(account_names) > 1 else _('Bank Account')
            res += '\n%s: %s' % (title, ', '.join(name for id, name in account_names))
        self.rml_footer = res
        self.rml_footer_readonly = res

    @api.onchange('state_id')
    def onchange_state(self):
        if self.state_id:
            self.country_id = self.state_id.country_id.id

    @api.onchange('font', 'rml_header', 'rml_header2', 'rml_header3')
    def onchange_font_name(self):
        """ To change default header style of all <para> and drawstring. """

        def _change_header(header, font):
            """ Replace default fontname use in header and setfont tag """

            default_para = re.sub('fontName.?=.?".*"', 'fontName="%s"' % font, header)
            return re.sub('(<setFont.?name.?=.?)(".*?")(.)', '\g<1>"%s"\g<3>' % font, default_para)

        if not self.font:
            return True
        self.rml_header = _change_header(self.rml_header, self.font.name)
        self.rml_header2 = _change_header(self.rml_header2, self.font.name)
        self.rml_header3 = _change_header(self.rml_header3, self.font.name)

    @api.onchange('country_id')
    def onchange_country(self):
        res = {'domain': {'state_id': []}}
        currency_id = self._get_euro()
        if self.country_id:
            currency_id = self.country_id.currency_id.id
            res['domain'] = {'state_id': [('country_id', '=', self.country_id.id)]}
        self.currency_id = currency_id
        return res

    name = fields.Char(related='partner_id.name', string='Company Name',
                       required=True, store=True)
    parent_id = fields.Many2one('res.company', string='Parent Company', index=True)
    child_ids = fields.One2many('res.company', 'parent_id', string='Child Companies')
    partner_id = fields.Many2one('res.partner', string='Partner', required=True)
    rml_header = fields.Text(required=True, default=_get_header)
    rml_header1 = fields.Char(string='Company Tagline',
        help="Appears by default on the top right corner of your printed documents (report header).")
    rml_header2 = fields.Text(string='RML Internal Header', required=True,
                              default=_header2)
    rml_header3 = fields.Text(string='RML Internal Header for Landscape Reports', required=True,
                              default=_header3)
    rml_footer = fields.Text(string='Report Footer',
                             help="Footer text displayed at the bottom of all reports.")
    rml_footer_readonly = fields.Text(related='rml_footer', string='Report Footer', readonly=True)
    custom_footer = fields.Boolean(
        help="Check this to define the report footer manually. Otherwise it will be filled in automatically.")
    font = fields.Many2one(
        'res.font', string="Font",
        default=lambda self: self._get_font(),
        domain=[('mode', 'in', ('Normal', 'Regular', 'all', 'Book'))],
        help="Set the font into the report header, it will be used as default font in the RML reports of the user company")
    logo = fields.Binary(related='partner_id.image', default=_get_logo)
    logo_web = fields.Binary(compute='_get_logo_web', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self._get_euro(),
                                  required=True)
    user_ids = fields.Many2many('res.users', 'res_company_users_rel', 'cid', 'user_id',
                                string='Accepted Users')
    account_no = fields.Char(string='Account No.')
    street = fields.Char(compute='_get_address_data', inverse='_set_address_data_street',
                         string="Street")
    street2 = fields.Char(compute='_get_address_data', inverse='_set_address_data_street2',
                          string="Street2")
    zip = fields.Char(compute='_get_address_data', inverse='_set_address_data_zip')
    city = fields.Char(compute='_get_address_data', inverse='_set_address_data_city')
    state_id = fields.Many2one('res.country.state', compute='_get_address_data',
                               inverse='_set_address_data_state',
                               string="Fed. State")
    bank_ids = fields.One2many('res.partner.bank', 'company_id', string='Bank Accounts',
                               help='Bank accounts related to this company')
    country_id = fields.Many2one('res.country', compute='_get_address_data',
                                 inverse='_set_address_data_country',
                                 string="Country")
    email = fields.Char(related='partner_id.email', string="Email", store=True)
    phone = fields.Char(related='partner_id.phone', string="Phone", store=True)
    fax = fields.Char(compute='_get_address_data', inverse='_set_address_data_fax')
    website = fields.Char(related='partner_id.website')
    vat = fields.Char(related='partner_id.vat', string="Tax ID")
    company_registry = fields.Char()
    rml_paper_format = fields.Selection([('a4', 'A4'), ('us_letter', 'US Letter')],
                                        string="Paper Format", required=True,
                                        default='a4',
                                        oldname='paper_format')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', _('The company name must be unique !'))
    ]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        context = dict(self.env.context or {})
        if context.pop('user_preference', None):
            # We browse as superuser. Otherwise, the user would be able to
            # select only the currently visible companies (according to rules,
            # which are probably to allow to see the child companies) even if
            # she belongs to some other companies.
            cmp_ids = list(set([self.env.user.company_id.id] + [
                cmp.id for cmp in self.env.user.company_ids]))
            args = (args or []) + [('id', 'in', cmp_ids)]
        return super(ResCompany, self.sudo()).name_search(
            name=name, args=args, operator=operator, limit=limit)

    @api.returns('self')
    def _company_default_get(self, cr, uid, object=False, field=False, context=None):
        """
        Returns the default company (the user's company)
        The 'object' and 'field' arguments are ignored but left here for
        backward compatibility and potential override.
        """
        return self.pool['res.users']._get_company(cr, uid, context=context)

    @tools.ormcache('uid', 'company')
    def _get_company_children(self, company=None):
        if not company:
            return []
        ids = self.search([('parent_id', 'child_of', [company])])
        return ids

    @api.multi
    def _get_partner_hierarchy(self, company_id):
        if company_id:
            if self.parent_id:
                return self._get_partner_hierarchy(self.parent_id.id)
            else:
                return self._get_partner_descendance(company_id, [])

    def _get_partner_descendance(self, company_id, descendance):
        descendance.append(self.partner_id.id)
        for child_id in self._get_company_children(company_id):
            if child_id != company_id:
                descendance = self._get_partner_descendance(child_id, descendance)
        return descendance

    #
    # This function restart the cache on the _get_company_children method
    #
    def cache_restart(self):
        self._get_company_children.clear_cache(self)

    @api.model
    def create(self, vals):
        if not vals.get('name', False) or vals.get('partner_id', False):
            self.cache_restart()
            return super(ResCompany, self).create(vals)
        partner = self.env['res.partner'].create({'name': vals['name'],
                                                  'is_company': True,
                                                 'image': vals['logo']})
        vals.update({'partner_id': partner.id})
        self.cache_restart()
        company = super(ResCompany, self).create(vals)
        partner.write({'company_id': company.id})
        return company

    @api.multi
    def write(self, values):
        self.cache_restart()
        return super(ResCompany, self).write(values)

    _constraints = [
        (osv.osv._check_recursion, _(
            'Error! You can not create recursive companies.'), ['parent_id'])
    ]
