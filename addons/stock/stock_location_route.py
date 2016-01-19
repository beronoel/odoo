# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _

#----------------------------------------------------------
# Routes
#----------------------------------------------------------
class StockLocationRoute(models.Model):
    _name = 'stock.location.route'
    _description = "Inventory Routes"
    _order = 'sequence'

    name = fields.Char('Route Name', required=True, translate=True)
    sequence = fields.Integer(default=0)
    pull_ids = fields.One2many('procurement.rule', 'route_id', 'Procurement Rules', copy=True)
    active = fields.Boolean(default=True, help="If the active field is set to False, it will allow you to hide the route without removing it.")
    push_ids = fields.One2many('stock.location.path', 'route_id', 'Push Rules', copy=True)
    product_selectable = fields.Boolean('Applicable on Product', default=True, help="When checked, the route will be selectable in the Inventory tab of the Product form.  It will take priority over the Warehouse route. ")
    product_categ_selectable = fields.Boolean('Applicable on Product Category', help="When checked, the route will be selectable on the Product Category.  It will take priority over the Warehouse route. ")
    warehouse_selectable = fields.Boolean('Applicable on Warehouse', help="When a warehouse is selected for this route, this route should be seen as the default route when products pass through this warehouse.  This behaviour can be overridden by the routes on the Product/Product Categories or by the Preferred Routes on the Procurement")
    supplied_wh_id = fields.Many2one('stock.warehouse', 'Supplied Warehouse')
    supplier_wh_id = fields.Many2one('stock.warehouse', 'Supplying Warehouse')
    company_id = fields.Many2one('res.company', 'Company', select=1, default=lambda self: self.env.user.company_id, help='Leave this field empty if this route is shared between all companies')
    product_ids = fields.Many2many('product.template', 'stock_route_product', 'route_id', 'product_id', 'Products')
    categ_ids = fields.Many2many('product.category', 'stock_location_route_categ', 'route_id', 'categ_id', 'Product Categories')
    warehouse_ids = fields.Many2many('stock.warehouse', 'stock_route_warehouse', 'route_id', 'warehouse_id', 'Warehouses')

    @api.multi
    def write(self, vals):
        '''when a route is deactivated, deactivate also its pull and push rules'''
        res = super(StockLocationRoute, self).write(vals)
        if 'active' in vals:
            push_ids = []
            pull_ids = []
            for route in self:
                if route.push_ids:
                    push_ids += [r.id for r in route.push_ids if r.active != vals['active']]
                if route.pull_ids:
                    pull_ids += [r.id for r in route.pull_ids if r.active != vals['active']]
            if push_ids:
                self.env['stock.location.path'].browse(push_ids).write({'active': vals['active']})
            if pull_ids:
                self.env['procurement.rule'].browse(pull_ids).write({'active': vals['active']})
        return res

    @api.multi
    def view_product_ids(self):
        return {
            'name': _('Products'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'product.template',
            'type': 'ir.actions.act_window',
            'domain': [('route_ids', 'in', self.ids[0])],
        }

    @api.multi
    def view_categ_ids(self):
        return {
            'name': _('Product Categories'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'product.category',
            'type': 'ir.actions.act_window',
            'domain': [('route_ids', 'in', self.ids[0])],
        }
