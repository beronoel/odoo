# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
