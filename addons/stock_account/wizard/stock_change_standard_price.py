# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
import openerp.addons.decimal_precision as dp


class ChangeStandardPrice(models.TransientModel):
    _name = "stock.change.standard.price"
    _description = "Change Standard Price"

    new_price = fields.Float('Price', required=True, digits_compute=dp.get_precision('Product Price'),
        help="If cost price is increased, stock variation account will be debited "
             "and stock output account will be credited with the value = (difference of amount * quantity available).\n"
             "If cost price is decreased, stock variation account will be creadited and stock input account will be debited.")

    @api.model
    def default_get(self, fields):
        if self.env.context.get("active_model") == 'product.product':
            Product = self.env['product.product']
        else:
            Product = self.env['product.template']
        product = Product.browse(self.env.context.get('active_id'))

        res = super(ChangeStandardPrice, self).default_get(fields)

        price = product.standard_price

        if 'new_price' in fields:
            res['new_price'] = price
        return res

    @api.multi
    def change_price(self):
        self.ensure_one()
        rec_id = self.env.context.get('active_id', False)
        assert rec_id, _('Active ID is not set in Context.')
        if self.env.context.get("active_model") == 'product.product':
            rec_id = self.env['product.product'].browse(rec_id).product_tmpl_id.id

        self.env['product.template'].browse(rec_id).do_change_standard_price(self.new_price)
        return {'type': 'ir.actions.act_window_close'}
