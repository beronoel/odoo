# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


class StockMoveConsume(models.TransientModel):
    _name = "stock.move.consume"
    _description = "Consume Products"

    product_id = fields.Many2one('product.product', string='Product', required=True, select=True)
    product_qty = fields.Float(string='Quantity', digits_compute=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', required=True)
    location_id = fields.Many2one('stock.location', string='Location', required=True)
    restrict_lot_id = fields.Many2one('stock.production.lot', string='Lot')

    #TOFIX: product_uom should not have different category of default UOM of product. Qty should be convert into UOM of original move line before going in consume and scrap
    @api.model
    def default_get(self, fields):

        res = super(StockMoveConsume, self).default_get(fields)
        move = self.env['stock.move'].browse(self._context['active_id'])
        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_uom_qty})
        if 'location_id' in fields:
            res.update({'location_id': move.location_id.id})
        return res

    @api.multi
    def do_move_consume(self):
        MoveObj = self.env['stock.move']
        move_ids = self._context['active_ids']
        for data in self:
            if move_ids and move_ids[0]:
                move = MoveObj.browse(move_ids[0])
            qty = self.env['product.uom']._compute_qty(data['product_uom'].id, data.product_qty, data.product_id.uom_id.id)
            MoveObj.action_consume(move_ids, qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id)
        return {'type': 'ir.actions.act_window_close'}
