# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from datetime import date
from dateutil.relativedelta import relativedelta
import odoo.addons.decimal_precision as dp


class MembershipInvoice(models.TransientModel):
    """Membership Invoice"""

    _name = "membership.invoice"
    _description = "Membership Invoice"
    product_id = fields.Many2one('product.product', 'Membership', required=True)
    member_price = fields.Float('Member Price', digits=dp.get_precision('Product Price'), required=True)
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    duration = fields.Integer(string='Duration (days)', help='The duration in days of the membership. If equal to 0, start and stop date are fixed.')

    @api.onchange('product_id')
    def onchange_product(self):
        """This function returns value of product's member price based on product id.
        """
        if not self.product_id:
            self.member_price = False
            self.duration = 0
        else:
            self.member_price = self.product_id.price_get()[self.product_id.id]
            self.date_from = self.product_id.membership_date_from
            self.date_to = self.product_id.membership_date_to
            self.duration = self.product_id.membership_duration

    @api.multi
    def membership_invoice(self):
        partner_id = None
        datas = {}
        pid = self.env.context.get('active_ids')
        date3 = date.today();
		date4 = date3 + relativedelta(months=+1))
        if self:
            if self.duration = 0 
			datas.update(membership_product_id=self.product_id.id,
                         amount=self.member_price,
                         date_from= date3,
                         date_to= date4)
			else
            datas.update(membership_product_id=self.product_id.id,
                         amount=self.member_price,
                         date_from=self.date_from,
                         date_to=self.date_to)
        if pid:
            invoice_list = self.env['res.partner'].browse(pid).create_membership_invoice(datas=datas)

        try:
            search_view_id = self.env.ref('account.view_account_invoice_filter').id
        except ValueError:
            search_view_id = False
        try:
            form_view_id = self.env.ref('account.invoice_form').id
        except ValueError:
            form_view_id = False

        return {
            'domain': [('id', 'in', invoice_list)],
            'name': 'Membership Invoices',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree'), (form_view_id, 'form')],
            'search_view_id': search_view_id,
        }
