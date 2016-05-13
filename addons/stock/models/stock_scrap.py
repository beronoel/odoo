# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError


class StockScrap(models.Model):
    _name = 'stock.scrap'
    _order = 'id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _('New'), states={'done': [('readonly', True)]}, string="Reference")
    product_id = fields.Many2one('product.product', 'Product', states={'done': [('readonly', True)]}, required=True)
    product_uom_id = fields.Many2one('product.uom', string='Unit of Measure', states={'done': [('readonly', True)]}, required=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot', states={'done': [('readonly', True)]}, domain="[('product_id', '=', product_id)]")
    package_id = fields.Many2one('stock.production.lot', 'Lot', states={'done': [('readonly', True)]})
    owner_id = fields.Many2one('res.partner', 'Owner', states={'done': [('readonly', True)]})
    picking_id = fields.Many2one('stock.picking', 'Picking', states={'done': [('readonly', True)]})
    location_id = fields.Many2one('stock.location', 'Location', states={'done': [('readonly', True)]}, required=True, domain="[('usage', '=', 'internal')]")
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", states={'done': [('readonly', True)]}, string="Scrap Location", default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
    scrap_qty = fields.Float('Quantity', states={'done': [('readonly', True)]}, required=True, default=1.0)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default="draft")
    move_id = fields.Many2one('stock.move', 'Stock Move', readonly=True)
    tracking = fields.Selection(related="product_id.tracking")
    origin = fields.Char(string='Source Document')
    date_expected = fields.Datetime(string='Expected Date', default=fields.Datetime.now)

    @api.model
    def default_get(self, fields):
        rec = super(StockScrap, self).default_get(fields)
        context = dict(self._context or {})
        if context.get('active_model') == 'stock.picking':
            if context.get('active_id'):
                picking = self.env['stock.picking'].browse(context['active_id'])
                rec.update({
                            'picking_id': picking.id,
                            'origin': picking.name,
                            'location_id': (picking.state == 'done') and picking.location_dest_id.id,
                            })
        elif not context.get('active_model'):
            location_id = self.env.ref('stock.stock_location_stock').id
            rec.update({'location_id': location_id})
        return rec

    @api.model
    def create(self, vals):
        if 'name' not in vals or vals['name'] == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.scrap') or _('New')
        scrap = super(StockScrap, self).create(vals)
        scrap.do_scrap()
        return scrap

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id

    def _prepare_move(self):
        vals = {'name': self.name,
            'origin': self.origin,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.scrap_qty,
            'location_id': self.location_id.id,
            'scrapped': True,
            'location_dest_id': self.scrap_location_id.id,
            'restrict_lot_id': self.lot_id.id,
            'restrict_partner_id': self.owner_id.id,
            'picking_id': self.picking_id.id,}
        return vals

    def _get_preferred_domain(self):
        self.ensure_one()
        preferred_domain_list=[]
        if self.picking_id:
            dest_loc = self.picking_id.location_dest_id.id
            if self.picking_id.state == 'done':
                preferred_domain = [('history_ids', 'in', self.picking_id.move_lines.filtered(lambda x: x.state == 'done')).ids]
                preferred_domain2 = [('history_ids', 'not in', self.picking_id.move_lines.filtered(lambda x: x.state == 'done')).ids]
                preferred_domain_list = [preferred_domain, preferred_domain2]
            else:
                preferred_domain = [('reservation_id', 'in', self.picking_id.move_lines.ids)]
                preferred_domain2 = [('reservation_id', '=', False)]
                preferred_domain3 = ['&', ('reservation_id', 'not in', self.picking_id.move_lines.ids), ('reservation_id', '!=', False)]
                preferred_domain_list = [preferred_domain, preferred_domain2, preferred_domain3]
        return preferred_domain_list

    @api.multi
    def do_scrap(self):
        self.ensure_one()
        StockMove = self.env['stock.move']
        vals = self._prepare_move()
        move = StockMove.create(vals)
        domain = [('qty', '>', 0), ('lot_id', '=', self.lot_id.id), 
                  ('package_id', '=', self.package_id.id)]
        preferred_domain_list = self._get_preferred_domain()
        quants = self.env['stock.quant'].quants_get_preferred_domain(move.product_qty, move, domain=domain, preferred_domain_list=preferred_domain_list)
        if any([not x[0] for x in quants]):
            raise UserError(_('You can only scrap something that is in stock in the system.  Maybe you forgot to enter something in the system or you need to correct with an Inventory Adjustment first'))
        self.env['stock.quant'].quants_reserve(quants, move)
        move.action_done()
        self.write({'move_id': move.id, 'state': 'done'})
        return True

    @api.multi
    def button_stock_picking(self):
        self.ensure_one()
        return {
            'name': _('Stock Operations'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.picking',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', '=', self.picking_id.id)],
        }

    @api.multi
    def button_stock_move(self):
        self.ensure_one()
        action = self.env.ref('stock.stock_move_action').read([])[0]
        action['domain'] = [('id', '=', self.move_id.id)]
        return action

    @api.multi
    def button_done(self):
        return {'type': 'ir.actions.act_window_close'}
