# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from openerp import api, fields, models

_logger = logging.getLogger(__name__)


class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    move_id = fields.Many2one('stock.move', string="Move line", help="If the invoice was generated from a stock.picking, reference to the related move line.")

    @api.model
    def move_line_get(self, invoice_id):
        res = super(AccountInvoiceLine, self).move_line_get(invoice_id)
        if self.company_id.anglo_saxon_accounting:
            inv = self.env['account.invoice'].browse(invoice_id)
            if inv.type in ('out_invoice', 'out_refund'):
                for i_line in inv.invoice_line_ids:
                    res.extend(self._anglo_saxon_sale_move_lines(i_line, res))
        return res

    def _get_price(self, inv, company_currency, i_line, price_unit):
        if inv.currency_id.id != company_currency:
            price = self.env['res.currency'].with_context({}, date=inv.date_invoice).compute(company_currency, inv.currency_id.id, price_unit * i_line.quantity)
        else:
            price = price_unit * i_line.quantity
        return round(price, inv.currency_id.decimal_places)

    def get_invoice_line_account(self, inv_type, product, fpos, company):
        if self.company_id.anglo_saxon_accounting and inv_type in ('in_invoice', 'in_refund'):
            accounts = product.product_tmpl_id.get_product_accounts(fpos)
            if inv_type == 'in_invoice':
                return accounts['stock_input']
            return accounts['stock_ouput']
        return super(AccountInvoiceLine, self).get_invoice_line_account(inv_type, product, fpos, company)

    @api.model
    def _anglo_saxon_sale_move_lines(self, i_line, res):
        """Return the additional move lines for sales invoices and refunds.

        i_line: An account.invoice.line object.
        res: The move line entries produced so far by the parent move_line_get.
        """
        inv = i_line.invoice_id
        company_currency = inv.company_id.currency_id.id

        if i_line.product_id.type == 'product' and i_line.product_id.valuation == 'real_time':
            # debit account dacc will be the output account
            # first check the product, if empty check the category
            dacc = i_line.product_id.property_stock_account_output_id and i_line.product_id.property_stock_account_output_id.id
            if not dacc:
                dacc = i_line.product_id.categ_id.property_stock_account_output_categ_id and i_line.product_id.categ_id.property_stock_account_output_categ_id.id
            # in both cases the credit account cacc will be the expense account
            # first check the product, if empty check the category
            cacc = i_line.product_id.property_account_expense_id and i_line.product_id.property_account_expense_id.id
            if not cacc:
                cacc = i_line.product_id.categ_id.property_account_expense_categ_id and i_line.product_id.categ_id.property_account_expense_categ_id.id
            if dacc and cacc:
                if i_line.move_id:
                    price = i_line.move_id.product_id.standard_price
                    from_unit = i_line.move_id.product_tmpl_id.uom_id.id
                    to_unit = i_line.move_id.product_uom.id
                    price_unit = self.env['product.uom']._compute_price(from_unit, price, to_uom_id=to_unit)
                else:
                    price_unit = i_line.product_id.standard_price
                return [
                    {
                        'type':'src',
                        'name': i_line.name[:64],
                        'price_unit':price_unit,
                        'quantity':i_line.quantity,
                        'price':self._get_price(inv, company_currency, i_line, price_unit),
                        'account_id':dacc,
                        'product_id':i_line.product_id.id,
                        'uom_id':i_line.uom_id.id,
                        'account_analytic_id': False,
                        'taxes':i_line.invoice_line_tax_ids,
                    },

                    {
                        'type':'src',
                        'name': i_line.name[:64],
                        'price_unit':price_unit,
                        'quantity':i_line.quantity,
                        'price': -1 * self._get_price(inv, company_currency, i_line, price_unit),
                        'account_id':cacc,
                        'product_id':i_line.product_id.id,
                        'uom_id':i_line.uom_id.id,
                        'account_analytic_id': False,
                        'taxes':i_line.invoice_line_tax_ids,
                    },
                ]
        return []


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.model
    def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None):
        invoice_data = super(AccountInvoice, self)._prepare_refund(invoice, date, date, description, journal_id)
        #for anglo-saxon accounting
        if invoice.company_id.anglo_saxon_accounting and invoice.type == 'in_invoice':
            Product = self.env['product.product']
            for dummy, dummy, line_dict in invoice_data['invoice_line_ids']:
                if line_dict.get('product_id'):
                    product = Product.browse(line_dict['product_id'])
                    counterpart_acct_id = product.property_stock_account_output_id and \
                            product.property_stock_account_output_id.id
                    if not counterpart_acct_id:
                        counterpart_acct_id = product.categ_id.property_stock_account_output_categ_id and \
                                product.categ_id.property_stock_account_output_categ_id.id
                    if counterpart_acct_id:
                        line_dict['account_id'] = invoice.fiscal_position_id.map_account(counterpart_acct_id)
        return invoice_data
