# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError


class Bank(models.Model):
    _name = 'res.bank'
    _description = 'Bank'
    _order = 'name'

    name = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char(change_default=True)
    city = fields.Char()
    state = fields.Many2one("res.country.state", string='Fed. State',
                            domain="[('country_id', '=', country)]")
    country = fields.Many2one('res.country')
    email = fields.Char()
    phone = fields.Char()
    fax = fields.Char()
    active = fields.Boolean(default=True)
    bic = fields.Char(string='Bank Identifier Code',
                      help="Sometimes called BIC or Swift.")

    @api.multi
    def name_get(self):
        result = []
        for bank in self:
            result.append((bank.id, (bank.bic and (bank.bic + ' - ') or '') + bank.name))
        return result


class ResPartnerBankType(models.Model):
    _name = 'res.partner.bank.type'
    _description = 'Bank Account Type'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(size=64, required=True)
    field_ids = fields.One2many('res.partner.bank.type.field', 'bank_type_id',
                                string='Type Fields')
    format_layout = fields.Text(translate=True,
                                default=lambda *args: "%(bank_name)s: %(acc_number)s")


class ResPartnerBankTypeFields(models.Model):
    _name = 'res.partner.bank.type.field'
    _description = 'Bank type fields'
    _order = 'name'

    name = fields.Char(string='Field Name', required=True, translate=True)
    bank_type_id = fields.Many2one('res.partner.bank.type',
                                   string='Bank Type',
                                   required=True,
                                   ondelete='cascade')
    required = fields.Boolean()
    readonly = fields.Boolean()
    size = fields.Integer(string='Max. Size')


class ResPartnerBank(models.Model):
    '''Bank Accounts'''
    _name = "res.partner.bank"
    _rec_name = "acc_number"
    _description = __doc__
    _order = 'sequence'

    @api.multi
    def _bank_type_get(self):
        result = []
        for bank_type in self.env['res.partner.bank.type'].search([]):
            result.append((bank_type.code, bank_type.name))
        return result

    @api.model
    def _default_value(self, field):
        if field in ('country_id', 'state_id'):
            value = False
        else:
            value = ''
        if not self.env.context.get('address'):
            return value

        for address in self.env['res.partner'].resolve_2many_commands('address',
                                                                      self.env.context['address'],
                                                                      ['type', field]):
            if address.get('type') == 'default':
                return address.get(field, value)
            elif not address.get('type'):
                value = address.get(field, value)
        return value

    acc_number = fields.Char(string='Account Number', required=True)
    bank = fields.Many2one('res.bank')
    bank_bic = fields.Char(string='Bank Identifier Code')
    bank_name = fields.Char()
    owner_name = fields.Char(string='Account Owner Name',
                             default=lambda self: self._default_value('name'))
    street = fields.Char(default=lambda self: self._default_value('street'))
    zip = fields.Char(change_default=True, default=lambda self: self._default_value('zip'))
    city = fields.Char(default=lambda self: self._default_value('city'))
    country_id = fields.Many2one('res.country', string='Country',
                                 change_default=True,
                                 default=lambda self: self._default_value('country_id'))
    state_id = fields.Many2one("res.country.state", string='Fed. State',
                               change_default=True, domain="[('country_id','=',country_id)]")
    company_id = fields.Many2one('res.company', string='Company',
                                 ondelete='cascade',
                                 help="Only if this bank account belong to your company")
    partner_id = fields.Many2one('res.partner', string='Account Holder',
                                 ondelete='cascade', index=True,
                                 domain=['|', ('is_company', '=', True), ('parent_id', '=', False)])
    state = fields.Selection(_bank_type_get, string='Bank Account Type',
                             change_default=True,
                             default=lambda self: self._default_value('state_id'))
    sequence = fields.Integer()
    footer = fields.Boolean(string="Display on Reports",
                            help="Display this bank account on the footer of printed documents like invoices and sales orders.")
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  help="Currency of the bank account and its related journal.")

    @api.model
    def fields_get(self, allfields=None, context=None, write_access=True, attributes=None):
        res = super(ResPartnerBank, self).fields_get(allfields=allfields,
                                                     context=self.env.context,
                                                     write_access=write_access,
                                                     attributes=attributes)
        for type in self.env['res.partner.bank.type'].search([]):
            for field in type.field_ids:
                if field.name in res:
                    res[field.name].setdefault('states', {})
                    res[field.name]['states'][type.code] = [('readonly', field.readonly),
                                                            ('required', field.required)]
        return res

    @api.model
    def _prepare_name_get(self, bank_dicts):
        """ Format the name of a res.partner.bank.
            This function is designed to be inherited to add replacement fields.
            :param bank_dicts: a list of res.partner.bank dicts, as returned by the method read()
            :return: [(id, name), ...], as returned by the method name_get()
        """
        # prepare a mapping {code: format_layout} for all bank types
        BankType = self.env['res.partner.bank.type']
        bank_types = BankType.search([])
        bank_code_format = dict((bt.code, bt.format_layout) for bt in bank_types)

        res = []
        for data in bank_dicts:
            name = data['acc_number']
            if data['state'] and bank_code_format.get(data['state']):
                try:
                    if not data.get('bank_name'):
                        data['bank_name'] = _('BANK')
                    data = dict((k, v or '') for (k, v) in data.iteritems())
                    name = bank_code_format[data['state']] % data
                except Exception:
                    raise UserError(_("Bank account name formating error") + ': ' + _("Check the format_layout field set on the Bank Account Type."))
            if data.get('currency_id'):
                currency_name = self.env['res.currency'].browse(data['currency_id'][0]).name
                name += ' (' + currency_name + ')'
            res.append((data.get('id', False), name))
        return res

    @api.multi
    def name_get(self):
        bank_dicts = self.read(self.fields_get_keys())
        return self._prepare_name_get(bank_dicts)

    @api.onchange('company_id')
    def onchange_company_id(self):
        if self.company_id and self.company_id.partner_id:
            self.partner_id = self.company_id.partner_id.id
            self.footer = 1

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id is not False:
            self.owner_name = self.partner_id.name
            self.street = self.partner_id.street or False
            self.city = self.partner_id.city or False
            self.zip = self.partner_id.zip or False
            self.country_id = self.partner_id.country_id.id
            self.state_id = self.partner_id.state_id.id
