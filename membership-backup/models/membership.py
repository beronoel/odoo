# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import odoo.addons.decimal_precision as dp


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

    partner = fields.Many2one('res.partner', string='Partner', ondelete='cascade', index=1)
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

    @api.constrains('date_to')
    def _check_membership_date(self):
        """Check if membership product is not in the past """
        for line in self:
            if line.date_to and line.account_invoice_id.date_invoice and fields.Date.from_string(line.date_to) < fields.Date.from_string(line.account_invoice_id.date_invoice):
                raise UserError(_('Error, this membership product is out of date'))
