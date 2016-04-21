# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo import api, fields, models, _
import odoo.addons.decimal_precision as dp
from odoo.exceptions import UserError

STATE = [
    ('none', 'Non Member'),
    ('canceled', 'Cancelled Member'),
    ('old', 'Old Member'),
    ('waiting', 'Waiting Member'),
    ('invoiced', 'Invoiced Member'),
    ('free', 'Free Member'),
    ('paid', 'Paid Member'),
]


class MembershipLine(models.Model):
    _name = 'membership.membership_line'
    _description = __doc__
    _rec_name = 'partner'
    _order = 'id desc'

    @api.constrains('date_to')
    def _check_membership_date(self):
        """Check if membership product is not in the past """
        for line in self:
            if line.date_to and line.account_invoice_id.date_invoice and fields.Date.from_string(line.date_to) < fields.Date.from_string(line.account_invoice_id.date_invoice):
                raise UserError(_('Error, this membership product is out of date'))

    @api.depends('account_invoice_id.state', 'partner.membership_state')
    def _compute_state(self):
        """Compute the state lines """
        for line in self:
            if not line.account_invoice_id:
                line.state = 'canceled'
                continue
            istate = line.account_invoice_id.state
            state = 'none'
            if istate in ['draft', 'proforma']:
                state = 'waiting'
            elif istate == 'open':
                state = 'invoiced'
            elif istate == 'paid':
                state = 'paid'
                if line.account_invoice_id.mapped('payment_ids.invoice_ids').filtered(lambda inv: inv.type == 'out_refund'):
                    state = 'canceled'
            elif istate == 'cancel':
                state = 'canceled'
            line.state = state

    partner = fields.Many2one('res.partner', string='Partner', ondelete='cascade', index=True)
    membership_id = fields.Many2one('product.product', string="Membership", required=True)
    date_from = fields.Date(string='From', readonly=True)
    date_to = fields.Date(string='To', readonly=True)
    date_cancel = fields.Date(string='Cancel date')
    date = fields.Date(string='Join Date', help="Date on which member has joined the membership")
    member_price = fields.Float(string='Membership Fee', digits=dp.get_precision('Product Price'), required=True, help='Amount for the membership')
    account_invoice_line = fields.Many2one('account.invoice.line', string='Account Invoice line', readonly=True)
    account_invoice_id = fields.Many2one('account.invoice', related='account_invoice_line.invoice_id', string='Invoice', readonly=True)
    state = fields.Selection(compute='_compute_state', string='Membership Status', selection=STATE, store=True, help="""It indicates the membership status.
                    -Non Member: A member who has not applied for any membership.
                    -Cancelled Member: A member who has cancelled his membership.
                    -Old Member: A member whose membership date has expired.
                    -Waiting Member: A member who has applied for the membership and whose invoice is going to be created.
                    -Invoiced Member: A member whose invoice has been created.
                    -Paid Member: A member who has paid the membership amount.""")
    company_id = fields.Many2one('res.company', related='account_invoice_line.invoice_id.company_id', string="Company", readonly=True, store=True)


class Partner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _cron_update_membership(self):
        partners = self.search([('membership_state', '=', 'paid')])._model._store_set_values(self.env.cr, self.env.uid, self.ids, ['membership_state'], context=self.env.context)

    def _membership_state(self):
        """This Function return Membership State For Given Partner. """
        today_date = date.today()
        for partner in self:
            partner.membership_state = 'none'
            if partner.membership_cancel and today_date > fields.Date.from_string(partner.membership_cancel):
                partner.membership_state = 'free' if partner.free_member else 'canceled'
                continue
            if partner.membership_stop and today_date > fields.Date.from_string(partner.membership_stop):
                partner.membership_state = 'free' if partner.free_member else 'old'
                continue

            state = 4
            for mline in partner.member_lines:
                if fields.Date.from_string(mline.date_to) >= today_date:
                    if mline.account_invoice_line.invoice_id:
                        mstate = mline.account_invoice_line.invoice_id.state
                        if mstate == 'paid':
                            state = 0
                            if mline.account_invoice_line.invoice_id.mapped('payment_ids.invoice_ids').filtered(lambda inv: inv.type == 'out_refund'):                                        
                                state = 2
                            break
                        elif mstate == 'open' and state != 0:
                            state = 1
                        elif mstate == 'cancel' and state != 0 and state != 1:
                            state = 2
                        elif (mstate == 'draft' or mstate == 'proforma') and state != 0 and state != 1:
                            state = 3
            if state == 4:
                for mline in partner.member_lines:
                    if fields.Date.from_string(mline.date_from) < today_date and fields.Date.from_string(mline.date_to) < today_date and mline.date_from <= mline.date_to and (mline.account_invoice_line.invoice_id.state) == 'paid':
                        state = 5
                    else:
                        state = 6
            if state == 0:
                partner.membership_state = 'paid'
            elif state == 1:
                partner.membership_state = 'invoiced'
            elif state == 2:
                partner.membership_state = 'canceled'
            elif state == 3:
                partner.membership_state = 'waiting'
            elif state == 5:
                partner.membership_state = 'old'
            elif state == 6:
                partner.membership_state = 'none'
        if partner.free_member and state != 0:
            partner.membership_state = 'free'
        if partner.associate_member:
            partner.membership_state = partner.associate_member._membership_state()
        return partner.membership_state

    @api.depends('free_member', 'member_lines')
    def _compute_membership_date(self):
        """Return  date of membership"""
        if self.ids:
            ids_to_search = []
            for partner in self:
                if partner.associate_member:
                    ids_to_search.append(partner.associate_member.id)
                else:
                    ids_to_search.append(partner.id)
            self.env.cr.execute("""
                SELECT
                    p.id as id,
                    MIN(m.date_from) as membership_start,
                    MAX(m.date_to) as membership_stop,
                    MIN(CASE WHEN m.date_cancel is not null THEN 1 END) as membership_cancel
                FROM
                    res_partner p
                LEFT JOIN
                    membership_membership_line m
                    ON (m.partner = p.id)
                WHERE
                    p.id IN %s
                GROUP BY
                    p.id""", (tuple(ids_to_search), ))
            for record in self.env.cr.dictfetchall():
                partner = self.browse(record.pop('id')).update(record)

    @api.depends('member_lines.account_invoice_id.state', 'membership_state', 'associate_member', 'free_member')
    def _compute_membership_state(self):
        return self._membership_state()

    associate_member = fields.Many2one('res.partner', string='Associate Member', help="A member with whom you want to associate your membership.It will consider the membership state of the associated member.")
    member_lines = fields.One2many('membership.membership_line', 'partner', string='Membership')
    free_member = fields.Boolean(help="Select if you want to give free membership.")
    membership_amount = fields.Float(digits=(16, 2), help='The price negotiated by the partner')
    membership_state = fields.Selection(compute='_compute_membership_state', string='Current Membership Status', selection=STATE, store=True,
                                        help='It indicates the membership state.\n'
                                        '-Non Member: A partner who has not applied for any membership.\n'
                                        '-Cancelled Member: A member who has cancelled his membership.\n'
                                        '-Old Member: A member whose membership date has expired.\n'
                                        '-Waiting Member: A member who has applied for the membership and whose invoice is going to be created.\n'
                                        '-Invoiced Member: A member whose invoice has been created.\n'
                                        '-Paying member: A member who has paid the membership fee.')
    membership_start = fields.Date(compute='_compute_membership_date', store=True, help='Date from which membership becomes active.')
    membership_stop = fields.Date(compute='_compute_membership_date', store=True, help='Date until which membership remains active.')
    membership_cancel = fields.Date(compute='_compute_membership_date', store=True, help='Date on which membership has been cancelled')

    @api.constrains('associate_member')
    def _check_associate_member(self):
        """Check  Recursive  for Associated Members.
        """
        if not self._check_recursion(parent='associate_member'):
            raise UserError(_('Error ! You cannot create recursive associated members.'))

    def create_membership_invoice(self, product_id=None, datas=None):
        """ Create Customer Invoice of Membership for partners.
        @param datas: datas has dictionary value which consist Id of Membership product and Cost Amount of Membership.
                      datas = {'membership_product_id': None, 'amount': None}
        """
        AccountInv = self.env['account.invoice']
        InvoiceLine = self.env['account.invoice.line']
        product_id = product_id or datas.get('membership_product_id', False)
        amount = datas.get('amount', 0.0)
        invoice_list = []
        for partner in self:
            account_id = partner.property_account_receivable_id.id
            fpos_id = partner.property_account_position_id.id
            addr = partner.address_get(['invoice'])
            if partner.free_member:
                raise UserError(_("Partner is a free Member."))
            if not addr.get('invoice'):
                raise UserError(_("Partner doesn't have an address to make the invoice."))

            invoice_id = AccountInv.create({
                'partner_id': partner.id,
                'account_id': account_id,
                'fiscal_position_id': fpos_id
            })
            line_values = {
                'product_id': product_id,
                'price_unit': amount,
                'invoice_id': invoice_id,
            }
            # create a record in cache, apply on-change then revert back to a dictionary
            invoice_line = InvoiceLine.new(line_values)
            invoice_line._onchange_product_id()
            line_values = invoice_line._convert_to_write(invoice_line._cache)
            line_values['price_unit'] = amount
            invoice_id.write({'invoice_line_ids': [(0, 0, line_values)]})
            invoice_list.append(invoice_id.id)
            invoice_id.compute_taxes()
        return invoice_list


class Product(models.Model):
    _inherit = 'product.template'

    membership = fields.Boolean(help='Check if the product is eligible for membership.')
    membership_date_from = fields.Date(string='Membership Start Date', help='Date from which membership becomes active.')
    membership_date_to = fields.Date(string='Membership End Date', help='Date until which membership remains active.')

    _sql_constraints = [('membership_date_greater','check(membership_date_to >= membership_date_from)','Error ! Ending Date cannot be set before Beginning Date.')]


class Invoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_cancel(self):
        '''Create a 'date_cancel' on the membership_line object'''
        res = super(Invoice, self).action_cancel()
        today_date = fields.Date.today()
        membership_lines = self.env['membership.membership_line'].search([('account_invoice_line', 'in', self.mapped('invoice_line_ids').ids)])
        membership_lines.write({'date_cancel': today_date})
        return res


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    @api.multi
    def write(self, vals):
        res = super(AccountInvoiceLine, self).write(vals)
        MembershipLine = self.env['membership.membership_line']
        for line in self.filtered(lambda l: l.invoice_id.type == 'out_invoice'):
            membership_lines = MembershipLine.search([('account_invoice_line', '=', line.id)])
            if line.product_id.membership and not membership_lines:
                # Product line has changed to a membership product
                date_from = line.product_id.membership_date_from
                date_to = line.product_id.membership_date_to
                if line.invoice_id.date_invoice > date_from and line.invoice_id.date_invoice < date_to:
                    date_from = line.invoice_id.date_invoice
                MembershipLine.create({
                                'partner': line.invoice_id.partner_id.id,
                                'membership_id': line.product_id.id,
                                'member_price': line.price_unit,
                                'date': fields.Date.today(),
                                'date_from': date_from,
                                'date_to': date_to,
                                'account_invoice_line': line.id,
                                })
            if line.product_id and not line.product_id.membership and membership_lines:
                # Product line has changed to a non membership product
                membership_lines.unlink()
        return res

    @api.multi
    def unlink(self):
        """Remove Membership Line Record for Account Invoice Line
        """
        membership_lines = self.env['membership.membership_line'].search([('account_invoice_line', 'in', self.ids)])
        membership_lines.unlink()
        return super(AccountInvoiceLine, self).unlink()

    @api.model
    def create(self, vals):
        MembershipLine = self.env['membership.membership_line']
        result = super(AccountInvoiceLine, self).create(vals)
        membership_lines = MembershipLine.search([('account_invoice_line', '=', result.id)])
        if result.invoice_id.type == 'out_invoice' and result.product_id.membership and not membership_lines:
            # Product line is a membership product
            date_from = result.product_id.membership_date_from
            date_to = result.product_id.membership_date_to
            if result.invoice_id.date_invoice > date_from and result.invoice_id.date_invoice < date_to:
                date_from = result.invoice_id.date_invoice
            MembershipLine.create({
                        'partner': result.invoice_id.partner_id.id,
                        'membership_id': result.product_id.id,
                        'member_price': result.price_unit,
                        'date': fields.Date.today(),
                        'date_from': date_from,
                        'date_to': date_to,
                        'account_invoice_line': result.id,
                        })
        return result
