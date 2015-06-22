# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError

class stock_lot_split(models.TransientModel):
    _name = 'stock.lot.split'
    _description = 'Lot split'

    @api.one
    @api.depends('line_ids_exist', 'line_ids_create')
    def _compute_qty_done(self):
        self.qty_done = sum([x.product_qty for x in self.line_ids])

    @api.one
    @api.depends('pack_id')
    def _compute_only_create(self): #Not necessary as values are set with defaults
        picking_type = self.pack_id.picking_id.picking_type_id
        self.only_create = picking_type.use_create_lots and not picking_type.use_existing_lots

    pack_id = fields.Many2one('stock.pack.operation', 'Pack operation')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    product_id = fields.Many2one('product.product', 'Product', readonly=True)
    product_uom_id = fields.Many2one('product.uom', 'Product Unit of Measure', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number')
    line_ids = fields.One2many('stock.lot.split.line', 'split_id')
    line_ids_exist = fields.One2many('stock.lot.split.line', 'split_id', domain=[('created', '=', False)])
    line_ids_create = fields.One2many('stock.lot.split.line', 'split_id', domain=[('created','=',True)])
    qty_done = fields.Float('Processed Qty', digits=dp.get_precision('Product Unit of Measure'), compute='_compute_qty_done')
    only_create = fields.Boolean('Only text', compute='_compute_only_create')
    picking_type_id = fields.Many2one('stock.picking.type', related='pack_id.picking_id.picking_type_id')
    tracking = fields.Selection('Is Serial Number', related='product_id.tracking', readonly=True)

    @api.model
    def default_get(self, fields):
        res = {}
        active_id = self._context.get('active_id')
        if active_id:
            pack_op = self.env['stock.pack.operation'].browse(active_id)
            line_ids = []
            picking_type = pack_op.picking_id.picking_type_id
            only_create = picking_type.use_create_lots and not picking_type.use_existing_lots
            if pack_op.qty_done > 0:
                if pack_op.product_id.tracking == 'serial':
                    product_qty = 1.0
                else:
                    product_qty = pack_op.qty_done
                line_ids = [(0, 0, {'lot_id': not only_create and pack_op.lot_id.id or False,
                                    'product_qty': product_qty,
                                    'created': only_create,})]
            res = {
                'pack_id': pack_op.id,
                'product_id': pack_op.product_id.id,
                'product_uom_id': pack_op.product_uom_id.id,
                'product_qty': pack_op.product_qty,
                'qty_done': pack_op.qty_done,
                'lot_id': pack_op.lot_id.id,
                'only_create': only_create,
            }
            if only_create:
                res['line_ids_create'] = line_ids
            else:
                res['line_ids_exist'] = line_ids
        return res

    @api.multi
    def process(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError (_('Please provide at least one line to replace it with'))
        # Split pack operations
        firsttime = True
        totals_other = 0.0
        for line in self.line_ids:
            if line.lot_name:
                lot = self.env['stock.production.lot'].create({'name': line.lot_name, 'product_id': self.pack_id.product_id.id})
            else:
                lot = line.lot_id
            if firsttime:
                self.pack_id.write({'lot_id': lot.id,
                                   'qty_done': line.product_qty})
                firsttime = False
            else:
                pack_new = self.pack_id.copy()
                pack_new.write({'lot_id': lot.id,
                                'qty_done': line.product_qty,
                                'product_qty': line.product_qty})
                totals_other += line.product_qty
        old_qty = self.pack_id.product_qty
        if old_qty - totals_other > 0:
            self.pack_id.product_qty = self.pack_id.product_qty - totals_other
        else:
            self.pack_id.product_qty = 0.0

        # Reload as the operations where split
        return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'type': 'ir.actions.act_window',
                'res_id': self.pack_id.picking_id.id,
                }


class stock_lot_split_line(models.TransientModel):
    _name = 'stock.lot.split.line'
    _description = 'Lot split line'

    split_id = fields.Many2one('stock.lot.split')
    created = fields.Boolean('Created')
    lot_id = fields.Many2one('stock.production.lot')
    lot_name = fields.Char('Name')
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), default=1.0)
    tracking = fields.Char('Is Serial Number')