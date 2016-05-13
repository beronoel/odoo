# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpUnbuild(models.Model):
    _name = "mrp.unbuild"
    _description = "Unbuild Order"
    _inherit = ['mail.thread']
    _order = 'id desc'

    def _get_default_location_id(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
        except (ValueError):
            location = False
        return location

    def _get_default_location_dest_id(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
        except (ValueError):
            location = False
        return location

    name = fields.Char('Reference', copy=False, readonly=True)
    product_id = fields.Many2one(
        'product.product', 'Product',
        required=True, states={'done': [('readonly', True)]})
    product_qty = fields.Float(
        'Quantity',
        required=True, states={'done': [('readonly', True)]})
    product_uom_id = fields.Many2one(
        'product.uom', 'Unit of Measure',
        required=True, states={'done': [('readonly', True)]})
    bom_id = fields.Many2one(
        'mrp.bom', 'Bill of Material',
        domain=[('product_tmpl_id', '=', 'product_id.product_tmpl_id')],
        required=True, states={'done': [('readonly', True)]})  # Add domain
    mo_id = fields.Many2one(
        'mrp.production', 'Manufacturing Order',
        domain="[('product_id', '=', product_id), ('state', 'in', ['done', 'cancel'])]",
        states={'done': [('readonly', True)]})
    lot_id = fields.Many2one(
        'stock.production.lot', 'Lot',
        domain="[('product_id', '=', product_id)]",
        states={'done': [('readonly', True)]})
    location_id = fields.Many2one(
        'stock.location', 'Location',
        default=_get_default_location_id,
        required=True, states={'done': [('readonly', True)]})
    location_dest_id = fields.Many2one(
        'stock.location', 'Destination Location',
        default=_get_default_location_dest_id,
        required=True, states={'done': [('readonly', True)]})
    consume_line_ids = fields.One2many('stock.move', 
        'consume_unbuild_id', readonly=True)  # TDE: some string / help 
    produce_line_ids = fields.One2many(
        'stock.move', 'unbuild_id',
        readonly=True)  # TDE: some string / help ?
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')],
        default='draft', index=True)

    @api.onchange('mo_id')
    def onchange_mo_id(self):
        if self.mo_id:
            self.product_id = self.mo_id.product_id.id
            self.product_qty = self.mo_id.product_qty

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id)
            self.product_uom_id = self.product_id.uom_id.id

    @api.constrains('product_qty')
    def _check_qty(self):
        if self.product_qty <= 0:
            raise ValueError(_('Unbuild product quantity cannot be negative or zero!'))


    @api.multi
    def _generate_moves(self):
        for unbuild in self:
            bom = unbuild.bom_id
            factor = self.env['product.uom']._compute_qty(unbuild.product_uom_id.id, unbuild.product_qty, bom.product_uom_id.id)
            bom.explode(unbuild.product_id, factor / bom.product_qty, method=self._generate_move)
        return True

    @api.model
    def create(self, vals):
        if not vals.get('name', False):
            vals['name'] = self.env['ir.sequence'].next_by_code('mrp.unbuild') or 'New'
        unbuild = super(MrpUnbuild, self).create(vals)
        return unbuild

    def _make_unbuild_consume_line(self):
        data = {
            'name': self.name,
            'date': self.create_date,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'location_id': self.location_id.id,
            'location_dest_id': self.product_id.property_stock_production.id,
            'origin': self.name
        }
        rec = self.env['stock.move'].create(data)
        rec.action_confirm()
        self.consume_line_ids = rec
        return rec

    @api.multi
    def _generate_move(self, bom_line, quantity, **kw):
        self.ensure_one()
        data = {
            'name': self.name,
            'date': self.create_date,
            'bom_line_id': bom_line.id,
            'product_id': bom_line.product_id.id,
            'product_uom_qty': quantity,
            'product_uom': bom_line.product_uom_id.id,
            'procure_method': 'make_to_stock',
            'location_dest_id': self.location_dest_id.id,
            'location_id': self.product_id.property_stock_production.id,
            'unbuild_id': self.id,
        }
        return self.env['stock.move'].create(data)


    @api.multi
    def button_unbuild(self):
        self.ensure_one()
        self._make_unbuild_consume_line()
        self._generate_moves()
        #Search quants that passed production order
        consume_move = self.consume_line_ids[0]
        domain = [('qty', '>', 0)]
        qty = self.product_qty # Convert to qty on product UoM
        if self.mo_id:
            main_finished_moves = self.mo_id.move_finished_ids.filtered(lambda x: x.product_id.id == self.mo_id.product_id.id)
            domain = [('qty', '>', 0), ('history_ids', 'in', [x.id for x in main_finished_moves])]
            quants = self.env['stock.quant'].quants_get_preferred_domain(qty, consume_move, domain=domain, 
                                                                         preferred_domain_list=[], lot_id=self.lot_id.id)
        else:
            quants = self.env['stock.quant'].quants_get_preferred_domain(qty, consume_move, domain=domain, 
                                                                         preferred_domain_list=[], lot_id=self.lot_id.id)
        self.env['stock.quant'].quants_reserve(quants, consume_move)
        if consume_move.has_tracking != 'none':
            if not self.lot_id.id:
                raise UserError(_('Should have a lot for the finished product'))
            self.env['stock.move.lots'].create({'move_id': consume_move.id,
                                                'lot_id': self.lot_id.id,
                                                'quantity_done': consume_move.product_uom_qty,
                                                'quantity': consume_move.product_uom_qty})
        else:
            consume_move.quantity_done = consume_move.product_uom_qty
        consume_move.move_validate()
        original_quants = self.env['stock.quant']
        for quant in consume_move.quant_ids:
            original_quants |= quant.consumed_quant_ids
        for produce_move in self.produce_line_ids:
            if produce_move.has_tracking != 'none':
                original = original_quants.filtered(lambda x: x.product_id.id == produce_move.product_id.id)
                self.env['stock.move.lots'].create({'move_id': produce_move.id,
                                                    'lot_id': original and original[0].lot_id.id or False,
                                                    'quantity_done': produce_move.product_uom_qty,
                                                    'quantity': produce_move.product_uom_qty,})
            else:
                produce_move.quantity_done = produce_move.product_uom_qty
        self.produce_line_ids.move_validate()
        produced_quant_ids = self.env['stock.quant']
        for move in self.produce_line_ids:
            produced_quant_ids |= move.quant_ids.filtered(lambda x: x.qty > 0)
        self.consume_line_ids[0].quant_ids.write({'produced_quant_ids': [(6, 0, produced_quant_ids.ids)]})
        self.write({'state': 'done'})

    @api.multi
    def button_open_move(self):
        stock_moves = self.env['stock.move'].search(['|', ('unbuild_id', '=', self.id), ('consume_unbuild_id', '=', self.id)])
        return {
            'name': _('Stock Moves'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', stock_moves.ids)],
        }

    @api.multi
    def _get_consumed_quants(self):
        self.ensure_one()
        quants = self.env['stock.quant']
        for quant in self.consume_line_ids[0].reserved_quant_ids:
            quants = quants | quant.consumed_quant_ids
        return quants