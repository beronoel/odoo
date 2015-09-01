# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = 'product.template'

    property_valuation = fields.Selection([
        ('manual_periodic', 'Periodic (manual)'),
        ('real_time', 'Perpetual (automated)')],
        string='Inventory Valuation', copy=True,
        company_dependent=True, default='manual_periodic',
        help="If perpetual valuation is enabled for a product, the system will automatically create journal entries corresponding to stock moves, with product price as specified by the 'Costing Method'" \
             "The inventory variation account set on the product category will represent the current inventory value, and the stock input and stock output account will hold the counterpart moves for incoming and outgoing products.")
    valuation = fields.Char(compute='_get_valuation_type', inverse='_set_valuation_type')  # TDE FIXME: store it ?
    property_cost_method = fields.Selection([
        ('standard', 'Standard Price'),
        ('average', 'Average Price'),
        ('real', 'Real Price')],
        string="Costing Method", copy=True,
        company_dependent=True,
        help="""Standard Price: The cost price is manually updated at the end of a specific period (usually once a year).
                Average Price: The cost price is recomputed at each incoming shipment and used for the product valuation.
                Real Price: The cost price displayed is the price of the last outgoing product (will be use in case of inventory loss for example).""")
    cost_method = fields.Char(compute='_get_cost_method', inverse='_set_cost_method')  # TDE FIXME: store it ?
    property_stock_account_input_id = fields.Many2one(
        comodel_name='account.account',
        string='Stock Input Account',
        company_dependent=True,
        domain=[('deprecated', '=', False)],
        oldname="property_stock_account_input",
        help="When doing real-time inventory valuation, counterpart journal items for all incoming stock moves will be posted in this account, unless "
             "there is a specific valuation account set on the source location. When not set on the product, the one from the product category is used.")
    property_stock_account_output_id = fields.Many2one(
        comodel_name='account.account',
        string='Stock Output Account',
        company_dependent=True,
        domain=[('deprecated', '=', False)],
        oldname="property_stock_account_output",
        help="When doing real-time inventory valuation, counterpart journal items for all outgoing stock moves will be posted in this account, unless "
             "there is a specific valuation account set on the destination location. When not set on the product, the one from the product category is used.")

    @api.depends('property_cost_method')
    def _get_cost_method(self):
        for product in self:
            if product.property_cost_method:
                product.cost_method = product.property_cost_method
            else:
                product.cost_method = product.categ_id.property_cost_method

    @api.depends('property_valuation')
    def _get_valuation_type(self):
        for product in self:
            if product.property_valuation:
                product.valuation = product.property_valuation
            else:
                product.valuation = product.categ_id.property_valuation

    def _set_cost_method(self):
        self.write({'property_cost_method': self.cost_method})

    def _set_valuation_type(self):
        self.write({'property_valuation': self.valuation})

    @api.model
    def create(self, vals):
        if vals.get('cost_method'):
            vals['property_cost_method'] = vals.pop('cost_method')
        if vals.get('valuation'):
            vals['property_valuation'] = vals.pop('valuation')
        return super(ProductTemplate, self).create(vals)

    @api.onchange('type')
    def onchange_type_valuation(self):
        if self.type != 'product':
            self.valuation = 'manual_periodic'
        return {}

    def _get_product_accounts(self):
        """ Add the stock accounts related to product to the result of super()
        @return: dictionary which contains information regarding stock accounts and super (income+expense accounts)
        """
        accounts = super(ProductTemplate, self)._get_product_accounts()
        accounts['stock_input'] = self.property_stock_account_input_id or self.categ_id.property_stock_account_input_categ_id
        accounts['stock_output'] = self.property_stock_account_output_id or self.categ_id.property_stock_account_output_categ_id
        accounts['stock_valuation'] = self.categ_id.property_stock_valuation_account_id or False
        return accounts

    def get_product_accounts(self, fiscal_pos=None):
        """ Add the stock journal related to product to the result of super()
        @return: dictionary which contains all needed information regarding stock accounts and journal and super (income+expense accounts)
        """
        accounts = super(ProductTemplate, self).get_product_accounts(fiscal_pos=fiscal_pos)
        accounts['stock_journal'] = self.categ_id.property_stock_journal_id or False
        return accounts

    def do_change_standard_price(self, new_price):
        """ Changes the Standard Price of Product and creates an account move accordingly."""
        AccountMove = self.env['account.move']
        AccountMoveLine = self.env['account.move.line']
        locations = self.env['stock.location'].search([('usage', '=', 'internal'), ('company_id', '=', self.env.user.company_id.id)])
        for rec in self:
            datas = rec.get_product_accounts()
            for location in locations:
                product = rec.with_context(location=location.id, compute_child=False)
                diff = product.standard_price - new_price
                if not diff:
                    raise UserError(_("No difference between standard price and new price!"))
                for prod_variant in product.product_variant_ids:
                    qty = prod_variant.qty_available
                    if qty:
                        # Accounting Entries
                        move_vals = {
                            'journal_id': datas['stock_journal'].id,
                            'company_id': location.company_id.id,
                        }
                        account_move = AccountMove.create(move_vals)

                        if diff*qty > 0:
                            amount_diff = qty * diff
                            debit_account_id = datas['stock_account_input']
                            credit_account_id = datas['property_stock_valuation_account_id']
                        else:
                            amount_diff = qty * -diff
                            debit_account_id = datas['property_stock_valuation_account_id']
                            credit_account_id = datas['stock_account_output']

                        AccountMoveLine.create({
                            'name': _('Standard Price changed'),
                            'account_id': debit_account_id.id,
                            'debit': amount_diff,
                            'credit': 0,
                            'move_id': account_move.id,
                        })
                        AccountMoveLine.create({
                            'name': _('Standard Price changed'),
                            'account_id': credit_account_id.id,
                            'debit': 0,
                            'credit': amount_diff,
                            'move_id': account_move.id,
                        })
                        account_move.post()
            rec.write({'standard_price': new_price})
        return True
