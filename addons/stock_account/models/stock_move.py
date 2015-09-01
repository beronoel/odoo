# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from openerp import api, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.multi
    def action_done(self):
        self.product_price_update_before_done()
        res = super(StockMove, self).action_done()
        self.product_price_update_after_done()
        return res

    def _store_average_cost_price(self):
        if any([q.qty <= 0 for q in self.quant_ids]):
            #if there is a negative quant, the standard price shouldn't be updated
            return
        #Note: here we can't store a quant.cost directly as we may have moved out 2 units (1 unit to 5€ and 1 unit to 7€) and in case of a product return of 1 unit, we can't know which of the 2 costs has to be used (5€ or 7€?). So at that time, thanks to the average valuation price we are storing we will svaluate it at 6€
        average_valuation_price = 0.0
        for q in self.quant_ids:
            average_valuation_price += q.qty * q.cost
        average_valuation_price = average_valuation_price / self.product_qty
        # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
        self.product_id.sudo().with_context(force_company=self.company_id.id).write({'standard_price': average_valuation_price})
        self.write({'price_unit': average_valuation_price})

    def product_price_update_before_done(self):
        tmpl_dict = {}
        for move in self:
            #adapt standard price on incomming moves if the product cost_method is 'average'
            if (move.location_id.usage == 'supplier') and (move.product_id.cost_method == 'average'):
                product = move.product_id
                prod_tmpl_id = product.product_tmpl_id.id
                qty_available = product.product_tmpl_id.qty_available
                if tmpl_dict.get(prod_tmpl_id):
                    product_avail = qty_available + tmpl_dict[prod_tmpl_id]
                else:
                    tmpl_dict[prod_tmpl_id] = 0
                    product_avail = qty_available
                if product_avail <= 0:
                    new_std_price = move.price_unit
                else:
                    # Get the standard price
                    amount_unit = product.standard_price
                    new_std_price = ((amount_unit * product_avail) + (move.price_unit * move.product_qty)) / (product_avail + move.product_qty)
                tmpl_dict[prod_tmpl_id] += move.product_qty

                # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
                product.sudo().with_context(force_company=move.company_id.id).write({'standard_price': new_std_price})

    def product_price_update_after_done(self):
        '''
        This method adapts the price on the product when necessary
        '''
        for move in self:
            #adapt standard price on outgoing moves if the product cost_method is 'real', so that a return
            #or an inventory loss is made using the last value used for an outgoing valuation.
            if move.product_id.cost_method == 'real' and move.location_dest_id.usage != 'internal':
                #store the average price of the move on the move and product form
                move._store_average_cost_price()
