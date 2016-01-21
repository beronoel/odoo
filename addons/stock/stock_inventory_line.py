# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
import openerp.addons.decimal_precision as dp

class StockInventoryLine(models.Model):
    _name = "stock.inventory.line"
    _description = "Inventory Line"
    _order = "inventory_id, location_name, product_code, product_name, prodlot_name"

    @api.multi
    @api.depends('product_id.name', 'product_id.default_code')
    def _get_product_name_change(self):
        return self.env['stock.inventory.line'].search([('product_id', 'in', self.ids)]).ids

    @api.multi
    @api.depends('location_id.name', 'location_id.active')
    def _get_location_change(self):
        return self.env['stock.inventory.line'].search([('location_id', 'in', self.ids)]).ids

    @api.multi
    @api.depends('prod_lot_id.name')
    def _get_prodlot_change(self):
        return self.env['stock.inventory.line'].search([('prod_lot_id', 'in', self.ids)]).ids

    def _get_theoretical_qty(self):
        for line in self:
            quant_ids = line._get_quants()
            tot_qty = sum([x.qty for x in quant_ids])
            if line.product_uom_id and line.product_id.uom_id.id != line.product_uom_id.id:
                tot_qty = self.env["product.uom"]._compute_qty_obj(line.product_id.uom_id, tot_qty, line.product_uom_id)
            line.theoretical_qty = tot_qty

    inventory_id = fields.Many2one('stock.inventory', 'Inventory', ondelete='cascade', select=True)
    location_id = fields.Many2one('stock.location', 'Location', required=True, select=True)
    product_id = fields.Many2one('product.product', 'Product', required=True, select=True)
    package_id = fields.Many2one('stock.quant.package', 'Pack', select=True)
    product_uom_id = fields.Many2one('product.uom', 'Product Unit of Measure', required=True, default=lambda self=None: self.env.ref('product.product_uom_unit').id)
    product_qty = fields.Float('Checked Quantity', digits_compute=dp.get_precision('Product Unit of Measure'), default=0)
    company_id = fields.Many2one(related='inventory_id.company_id', relation='res.company', string='Company', store=True, select=True, readonly=True)
    prod_lot_id = fields.Many2one('stock.production.lot', 'Serial Number', domain="[('product_id','=',product_id)]")
    state = fields.Selection(related='inventory_id.state', string='Status', readonly=True)
    theoretical_qty = fields.Float(compute="_get_theoretical_qty", digits_compute=dp.get_precision('Product Unit of Measure'), readonly=True, string="Theoretical Quantity")
    partner_id = fields.Many2one('res.partner', 'Owner')
    product_name = fields.Char(related='product_id.name', string='Product Name', store=True)
    product_code = fields.Char(related='product_id.default_code', string='Product Code', store=True)
    # location_name = fields.Char(related='location_id.name', string='Location Name', store=True)
    location_name = fields.Char(related='location_id.complete_name', string='Location Name', store=True)
    prodlot_name = fields.Char(related='prod_lot_id.name', string='Serial Number Name', store=True)

    @api.model
    def create(self, values):
        if 'product_id' in values and 'product_uom_id' not in values:
            values['product_uom_id'] = self.env['product.product'].browse(values.get('product_id')).uom_id.id
        return super(StockInventoryLine, self).create(values)

    @api.model
    def _get_quants(self):
        dom = [('company_id', '=', self.company_id.id), ('location_id', '=', self.location_id.id), ('lot_id', '=', self.prod_lot_id.id),
                        ('product_id', '=', self.product_id.id), ('owner_id', '=', self.partner_id.id), ('package_id', '=', self.package_id.id)]
        quants = self.env["stock.quant"].search(dom)
        return quants

    @api.onchange("product_id", "product_uom_id", "location_id", "prod_lot_id", "package_id", "partner_id")
    def onchange_createline(self):
        res = {}
        # If no UoM already put the default UoM of the product
        if self.product_id:
            if self.product_id.uom_id.category_id.id != self.product_uom_id.category_id.id:
                self.product_uom_id = self.product_id.uom_id
                res['domain'] = {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
                # uom_id = product.uom_id.id
        # Calculate theoretical quantity by searching the quants as in quants_get
        if self.product_id and self.location_id:
            company_id = self.company_id
            if not self.company_id:
                company_id = self.env.user.company_id.id
            dom = [('company_id', '=', company_id.id), ('location_id', '=', self.location_id.id), ('lot_id', '=', self.prod_lot_id.id),
                        ('product_id', '=', self.product_id.id), ('owner_id', '=', self.partner_id.id), ('package_id', '=', self.package_id.id)]
            quants = self.env["stock.quant"].search(dom)
            th_qty = sum([x.qty for x in quants])
            if self.product_id and self.product_uom_id and self.product_id.uom_id.id != self.product_uom_id.id:
                th_qty = self.env["product.uom"]._compute_qty(self.product_id.uom_id.id, th_qty, self.product_uom_id)
            self.theoretical_qty = th_qty
            self.product_qty = th_qty
        return res

    @api.model
    def _resolve_inventory_line(self, inventory_line):
        stock_move_obj = self.env['stock.move']
        quant_obj = self.env['stock.quant']
        diff = inventory_line.theoretical_qty - inventory_line.product_qty
        if not diff:
            return
        #each theorical_lines where difference between theoretical and checked quantities is not 0 is a line for which we need to create a stock move
        vals = {
            'name': _('INV:') + (inventory_line.inventory_id.name or ''),
            'product_id': inventory_line.product_id.id,
            'product_uom': inventory_line.product_uom_id.id,
            'date': inventory_line.inventory_id.date,
            'company_id': inventory_line.inventory_id.company_id.id,
            'inventory_id': inventory_line.inventory_id.id,
            'state': 'confirmed',
            'restrict_lot_id': inventory_line.prod_lot_id.id,
            'restrict_partner_id': inventory_line.partner_id.id,
        }
        inventory_location_id = inventory_line.product_id.property_stock_inventory.id
        if diff < 0:
            #found more than expected
            vals['location_id'] = inventory_location_id
            vals['location_dest_id'] = inventory_line.location_id.id
            vals['product_uom_qty'] = -diff
        else:
            #found less than expected
            vals['location_id'] = inventory_line.location_id.id
            vals['location_dest_id'] = inventory_location_id
            vals['product_uom_qty'] = diff
        move = stock_move_obj.create(vals)
        # move = stock_move_obj.browse(cr, uid, move_id, context=context)
        if diff > 0:
            domain = [('qty', '>', 0.0), ('package_id', '=', inventory_line.package_id.id), ('lot_id', '=', inventory_line.prod_lot_id.id), ('location_id', '=', inventory_line.location_id.id)]
            preferred_domain_list = [[('reservation_id', '=', False)], [('reservation_id.inventory_id', '!=', inventory_line.inventory_id.id)]]
            quants = quant_obj.quants_get_preferred_domain(move.product_qty, move, domain=domain, preferred_domain_list=preferred_domain_list)
            quant_obj.quants_reserve(quants, move)
        elif inventory_line.package_id:
            move.action_done()
            quants = move.quant_ids
            quants.write({'package_id': inventory_line.package_id.id})
            res = quant_obj.search([('qty', '<', 0.0), ('product_id', '=', move.product_id.id),
                                    ('location_id', '=', move.location_dest_id.id), ('package_id', '!=', False)], limit=1)
            if res:
                for quant in move.quant_ids:
                    if quant.location_id.id == move.location_dest_id.id:  # To avoid we take a quant that was reconcile already
                        quant_obj._quant_reconcile_negative(quant, move)
        return move

    # Should be left out in next version
    @api.multi
    def restrict_change(self, theoretical_qty):
        return {}

    # Should be left out in next version
    @api.multi
    def on_change_product_id(self, product, uom, theoretical_qty):
        """ Changes UoM
        @param location_id: Location id
        @param product: Changed product_id
        @param uom: UoM product
        @return:  Dictionary of changed values
        """
        if not product:
            return {'value': {'product_uom_id': False}}
        obj_product = self.env['product.product'].browse(product)
        return {'value': {'product_uom_id': uom or obj_product.uom_id.id}}
