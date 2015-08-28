# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.osv import fields, osv
from openerp import api
import logging
_logger = logging.getLogger(__name__)


class account_invoice_line(osv.osv):
    _inherit = "account.invoice.line"

    _columns = {
        'move_id': fields.many2one('stock.move', string="Move line", help="If the invoice was generated from a stock.picking, reference to the related move line."),
    }

    def move_line_get(self, cr, uid, invoice_id, context=None):
        res = super(account_invoice_line,self).move_line_get(cr, uid, invoice_id, context=context)
        if self.company_id.anglo_saxon_accounting:
            inv = self.pool.get('account.invoice').browse(cr, uid, invoice_id, context=context)
            if inv.type in ('out_invoice','out_refund'):
                for i_line in inv.invoice_line_ids:
                    res.extend(self._anglo_saxon_sale_move_lines(cr, uid, i_line, res, context=context))
        return res

    def _get_price(self, cr, uid, inv, company_currency, i_line, price_unit):
        cur_obj = self.pool.get('res.currency')
        decimal_precision = self.pool.get('decimal.precision')
        if inv.currency_id.id != company_currency:
            price = cur_obj.compute(cr, uid, company_currency, inv.currency_id.id, price_unit * i_line.quantity, context={'date': inv.date_invoice})
        else:
            price = price_unit * i_line.quantity
        return round(price, inv.currency_id.decimal_places)

    @api.v8
    def get_invoice_line_account(self, type, product, fpos, company):
        if self.company_id.anglo_saxon_accounting and type in ('in_invoice', 'in_refund'):
            accounts = product.product_tmpl_id.get_product_accounts(fpos)
            if type == 'in_invoice':
                return accounts['stock_input']
            return accounts['stock_ouput']
        return super(account_invoice_line, self).get_invoice_line_account(type, product, fpos, company)

    def _anglo_saxon_sale_move_lines(self, cr, uid, i_line, res, context=None):
        """Return the additional move lines for sales invoices and refunds.

        i_line: An account.invoice.line object.
        res: The move line entries produced so far by the parent move_line_get.
        """
        inv = i_line.invoice_id
        company_currency = inv.company_id.currency_id.id

        if i_line.product_id.type == 'product' and i_line.product_id.valuation == 'real_time':
            # debit account dacc will be the output account
            # first check the product, if empty check the category
            dacc = i_line.product_id.property_stock_account_output and i_line.product_id.property_stock_account_output.id
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
                    price_unit = self.pool['product.uom']._compute_price(cr, uid, from_unit, price, to_uom_id=to_unit)
                else:
                    price_unit = i_line.product_id.standard_pric
                return [
                    {
                        'type':'src',
                        'name': i_line.name[:64],
                        'price_unit':price_unit,
                        'quantity':i_line.quantity,
                        'price':self._get_price(cr, uid, inv, company_currency, i_line, price_unit),
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
                        'price': -1 * self._get_price(cr, uid, inv, company_currency, i_line, price_unit),
                        'account_id':cacc,
                        'product_id':i_line.product_id.id,
                        'uom_id':i_line.uom_id.id,
                        'account_analytic_id': False,
                        'taxes':i_line.invoice_line_tax_ids,
                    },
                ]
        return []

class account_invoice(osv.osv):
    _inherit = "account.invoice"

    def _prepare_refund(self, cr, uid, invoice, date_invoice=None, date=None, description=None, journal_id=None, context=None):
        invoice_data = super(account_invoice, self)._prepare_refund(cr, uid, invoice, date, date,
                                                                    description, journal_id, context=context)
        #for anglo-saxon accounting
        if invoice.company_id.anglo_saxon_accounting and invoice.type == 'in_invoice':
            fiscal_position = self.pool.get('account.fiscal.position')
            for dummy, dummy, line_dict in invoice_data['invoice_line_ids']:
                if line_dict.get('product_id'):
                    product = self.pool.get('product.product').browse(cr, uid, line_dict['product_id'], context=context)
                    counterpart_acct_id = product.property_stock_account_output and \
                            product.property_stock_account_output.id
                    if not counterpart_acct_id:
                        counterpart_acct_id = product.categ_id.property_stock_account_output_categ_id and \
                                product.categ_id.property_stock_account_output_categ_id.id
                    if counterpart_acct_id:
                        fpos = invoice.fiscal_position_id or False
                        line_dict['account_id'] = fiscal_position.map_account(cr, uid,
                                                                              fpos,
                                                                              counterpart_acct_id)
        return invoice_data
