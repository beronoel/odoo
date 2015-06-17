# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError

class stock_lot_split(models.TransientModel):
    _name = 'stock.lot.split'
    _description = 'Lot split'

    @api.one
    @api.depends('line_ids')
    def _compute_qty_done(self):
        self.qty_done = sum([x.product_qty for x in self.line_ids])

    pack_id = fields.Many2one('stock.pack.operation', 'Pack operation')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    product_id = fields.Many2one('product.product', 'Product', readonly=True)
    product_uom_id = fields.Many2one('product.uom', 'Product Unit of Measure', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number')
    line_ids = fields.One2many('stock.lot.split.line', 'split_id')
    qty_done = fields.Float('Processed Qty', digits=dp.get_precision('Product Unit of Measure'), compute='_compute_qty_done')
    picking_type_id = fields.Many2one('stock.picking.type', related='pack_id.picking_id.picking_type_id')

    @api.model
    def default_get(self, fields):
        res = {}
        active_id = self._context.get('active_id')
        if active_id:
            pack_op = self.env['stock.pack.operation'].browse(active_id)
            line_ids = []
            if pack_op.qty_done > 0:
                if pack_op.product_id.tracking == 'serial':
                    product_qty = 1.0
                else:
                    product_qty = pack_op.qty_done
                line_ids = [(0, 0, {'lot_id': pack_op.lot_id.id,
                              'product_qty': product_qty})]
            res = {
                'pack_id': pack_op.id,
                'product_id': pack_op.product_id.id,
                'product_uom_id': pack_op.product_uom_id.id,
                'product_qty': pack_op.product_qty,
                'qty_done': pack_op.qty_done,
                'lot_id': pack_op.lot_id.id,
                'line_ids': line_ids,
            }

        return res

    @api.multi
    def process(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError (_('Please provide at least one line to replace it with'))
        #Calculate and check
        firsttime = True
        totals_other = 0.0
        for line in self.line_ids:
            if firsttime:
                self.pack_id.write({'lot_id': line.lot_id.id,
                                   'qty_done': line.product_qty})
                firsttime = False
            else:
                pack_new = self.pack_id.copy()
                pack_new.write({'lot_id': line.lot_id.id,
                                'qty_done': line.product_qty,
                                'product_qty': line.product_qty})
                totals_other += line.product_qty
        old_qty = self.pack_id.product_qty
        if old_qty - totals_other > 0:
            self.pack_id.product_qty = self.pack_id.product_qty - totals_other
        else:
            self.pack_id.product_qty = 0.0

        # Split pack operations
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


class stock_lot_split_line(models.TransientModel):
    _name = 'stock.lot.split.line'
    _description = 'Lot split line'

    split_id = fields.Many2one('stock.lot.split')
    lot_id = fields.Many2one('stock.production.lot')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), default=1.0)
    tracking = fields.Selection('Is Serial Number', related='split_id.product_id.tracking')