# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api
import openerp.addons.decimal_precision as dp

class stock_lot_split(models.TransientModel):
    _name = 'stock.lot.split'
    _description = 'Lot split'

    pack_id = fields.Many2one('stock.pack.operation', 'Pack operation')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    product_id = fields.Many2one('product.product', 'Product')
    product_uom_id = fields.Many2one('product.uom', 'Product Unit of Measure')
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number')
    line_ids = fields.One2many('stock.lot.split.line', 'split_id')
    qty_done = fields.Float('Processed Qty', digits=dp.get_precision('Product Unit of Measure'))

    @api.model
    def default_get(self, fields):
        res = {}
        active_id = self._context.get('active_id')
        if active_id:
            pack_op = self.env['stock.pack.operation'].browse(active_id)
            res = {
                'pack_id': pack_op.id,
                'product_id': pack_op.product_id.id,
                'product_uom_id': pack_op.product_uom_id.id,
                'product_qty': pack_op.product_qty,
                'qty_done': pack_op.qty_done,
                'lot_id': pack_op.lot_id.id,
            }
        return res

    @api.multi
    def process(self):
        self.ensure_one()
        return {}


class stock_lot_split_line(models.TransientModel):
    _name = 'stock.lot.split.line'
    _description = 'Lot split line'

    split_id = fields.Many2one('stock.lot.split')
    lot_id = fields.Many2one('stock.production.lot')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), default=1.0)



