# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api
import openerp.addons.decimal_precision as dp

class stock_lot_details(models.TransientModel):
    _name = 'stock.lot.details'
    _description = 'Lot details'



    pack_id = fields.Many2one('stock.pack.operation', 'Pack operation')
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number')

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
                'quantity': pack_op.product_qty,
                'qty_done': pack_op.qty_done,
                'package_id': pack_op.package_id.id,
                'lot_id': pack_op.lot_id.id,
                'location_id': pack_op.location_id.id,
                'location_dest_id': pack_op.location_dest_id.id,
                'result_package_id': pack_op.result_package_id.id,
            }
        return res

    @api.one
    def process(self):
        pack = self.pack_id
        pack.write({
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom_id.id,
                'qty_done': self.qty_done,
                'package_id': self.package_id.id,
                'lot_id': self.lot_id.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'result_package_id': self.result_package_id.id,
        })
        return {}