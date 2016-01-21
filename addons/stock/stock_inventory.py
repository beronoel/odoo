# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import time

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class StockInventory(models.Model):
    _name = "stock.inventory"
    _description = "Inventory"

    @api.multi
    def _get_move_ids_exist(self):
        for inv in self:
            inv.move_ids_exist = False
            if inv.move_ids:
                inv.move_ids_exist = True

    @api.model
    def _get_available_filters(self):
        """
           This function will return the list of filter allowed according to the options checked
           in 'Settings\Warehouse'.
           :rtype: list of tuple
        """
        #default available choices
        res_filter = [('none', _('All products')), ('partial', _('Select products manually')), ('product', _('One product only'))]
        settings_obj = self.env['stock.config.settings']
        stock_settings = settings_obj.search([], limit=1, order='id DESC')
        #If we don't have updated config until now, all fields are by default false and so should be not dipslayed
        if not stock_settings:
            return res_filter

        if stock_settings.group_stock_tracking_owner:
            res_filter.append(('owner', _('One owner only')))
            res_filter.append(('product_owner', _('One product for a specific owner')))
        if stock_settings.group_stock_tracking_lot:
            res_filter.append(('lot', _('One Lot/Serial Number')))
        if stock_settings.group_stock_packaging:
            res_filter.append(('pack', _('A Pack')))
        return res_filter

    @api.multi
    def _get_total_qty(self):
        for inv in self:
            inv.total_qty = sum([x.product_qty for x in inv.line_ids])

    @api.model
    def _default_stock_location(self):
        try:
            warehouse = self.env.ref('stock.warehouse0')
            return warehouse.lot_stock_id.id
        except:
            return False

    INVENTORY_STATE_SELECTION = [
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('confirm', 'In Progress'),
        ('done', 'Validated'),
    ]

    name = fields.Char('Inventory Reference', required=True, readonly=True, states={'draft': [('readonly', False)]}, help="Inventory Name.")
    date = fields.Datetime('Inventory Date', required=True, readonly=True, help="The date that will be used for the stock level check of the products and the validation of the stock move related to this inventory.", default=lambda self: fields.datetime.now())
    line_ids = fields.One2many(comodel_name='stock.inventory.line', inverse_name='inventory_id', string='Inventories', readonly=False, states={'done': [('readonly', True)]}, help="Inventory Lines.", copy=True)
    move_ids = fields.One2many(comodel_name='stock.move', inverse_name='inventory_id', string='Created Moves', help="Inventory Moves.", states={'done': [('readonly', True)]})
    state = fields.Selection(INVENTORY_STATE_SELECTION, 'Status', readonly=True, select=True, copy=False, default='draft')
    company_id = fields.Many2one('res.company', 'Company', required=True, select=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda self: self.env.user.company_id)
    location_id = fields.Many2one('stock.location', 'Inventoried Location', required=True, readonly=True, states={'draft': [('readonly', False)]}, default=_default_stock_location)
    product_id = fields.Many2one('product.product', 'Inventoried Product', readonly=True, states={'draft': [('readonly', False)]}, help="Specify Product to focus your inventory on a particular Product.")
    package_id = fields.Many2one('stock.quant.package', 'Inventoried Pack', readonly=True, states={'draft': [('readonly', False)]}, help="Specify Pack to focus your inventory on a particular Pack.")
    partner_id = fields.Many2one('res.partner', 'Inventoried Owner', readonly=True, states={'draft': [('readonly', False)]}, help="Specify Owner to focus your inventory on a particular Owner.")
    lot_id = fields.Many2one('stock.production.lot', 'Inventoried Lot/Serial Number', readonly=True, states={'draft': [('readonly', False)]}, help="Specify Lot/Serial Number to focus your inventory on a particular Lot/Serial Number.", copy=False)
    # technical field for attrs in view
    move_ids_exist = fields.Boolean(compute="get_move_ids_exist", string='Has Stock Moves', help='Check the existance of stock moves linked to this inventory')
    filter = fields.Selection(_get_available_filters, string='Inventory of', required=True, default='none',
        help="If you do an entire inventory, you can choose 'All Products' and it will prefill the inventory with the current stock.  If you only do some products  "\
        "(e.g. Cycle Counting) you can choose 'Manual Selection of Products' and the system won't propose anything.  You can also let the "\
        "system propose for a single product / lot /... ")
    total_qty = fields.Float(compute="_get_total_qty")

    @api.multi
    def reset_real_qty(self):
        self[0].line_ids.write({'product_qty': 0})
        return True

    @api.multi
    def action_done(self):
        """ Finish the inventory
        @return: True
        """
        for inv in self:
            for inventory_line in inv.line_ids:
                if inventory_line.product_qty < 0 and inventory_line.product_qty != inventory_line.theoretical_qty:
                    raise UserError(_('You cannot set a negative product quantity in an inventory line:\n\t%s - qty: %s' % (inventory_line.product_id.name, inventory_line.product_qty)))
            inv.action_check()
            inv.write({'state': 'done'})
            self.post_inventory(inv)
        return True

    # TO Do: temporary fix this method because method call in sale_mrp
    @api.model
    def post_inventory(self, inv):
        #The inventory is posted as a single step which means quants cannot be moved from an internal location to another using an inventory
        #as they will be moved to inventory loss, and other quants will be created to the encoded quant location. This is a normal behavior
        #as quants cannot be reuse from inventory location (users can still manually move the products before/after the inventory if they want).
        inv.move_ids.filtered(lambda x: x.state != 'done').action_done()

    @api.multi
    def action_check(self):
        """ Checks the inventory and computes the stock move to do
        @return: True
        """
        for inventory in self:
            #first remove the existing stock moves linked to this inventory
            inventory.move_ids.unlink()
            for line in inventory.line_ids:
                #compare the checked quantities on inventory lines to the theorical one
                self.env['stock.inventory.line']._resolve_inventory_line(line)
                # line._resolve_inventory_line()

    @api.multi
    def action_cancel_draft(self):
        """ Cancels the stock move and change inventory state to draft.
        @return: True
        """
        for inv in self:
            inv.write({'line_ids': [(5,)]})
            inv.move_ids.action_cancel()
            inv.write({'state': 'draft'})
        return True

    @api.multi
    def action_cancel_inventory(self):
        self.action_cancel_draft()

    @api.multi
    def prepare_inventory(self):
        for inventory in self:
            # If there are inventory lines already (e.g. from import), respect those and set their theoretical qty
            if not inventory.line_ids and inventory.filter != 'partial':
                #compute the inventory lines and create them
                vals = inventory._get_inventory_lines()
                for product_line in vals:
                    self.env['stock.inventory.line'].create(product_line)
        return self.write({'state': 'confirm', 'date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)})

    @api.multi
    def _get_inventory_lines(self):
        location_ids = self.env['stock.location'].search([('id', 'child_of', [self.location_id.ids])]).ids
        domain = ' location_id in %s'
        args = (tuple(location_ids),)
        if self.partner_id:
            domain += ' and owner_id = %s'
            args += (self.partner_id.id,)
        if self.lot_id:
            domain += ' and lot_id = %s'
            args += (self.lot_id.id,)
        if self.product_id:
            domain += ' and product_id = %s'
            args += (self.product_id.id,)
        if self.package_id:
            domain += ' and package_id = %s'
            args += (self.package_id.id,)

        self.env.cr.execute('''
           SELECT product_id, sum(qty) as product_qty, location_id, lot_id as prod_lot_id, package_id, owner_id as partner_id
           FROM stock_quant WHERE''' + domain + '''
           GROUP BY product_id, location_id, lot_id, package_id, partner_id
        ''', args)
        vals = []
        for product_line in self.env.cr.dictfetchall():
            #replace the None the dictionary by False, because falsy values are tested later on
            for key, value in product_line.items():
                if not value:
                    product_line[key] = False
            product_line['inventory_id'] = self.id
            product_line['theoretical_qty'] = product_line['product_qty']
            if product_line['product_id']:
                product = self.env['product.product'].browse(product_line['product_id'])
                product_line['product_uom_id'] = product.uom_id.id
            vals.append(product_line)
        return vals

    @api.multi
    @api.constrains('filter', 'product_id', 'lot_id', 'partner_id', 'package_id')
    def _check_filter_product(self):
        for inventory in self:
            if inventory.filter == 'none' and inventory.product_id and inventory.location_id and inventory.lot_id:
                return True
            if inventory.filter not in ('product', 'product_owner') and inventory.product_id:
                raise ValueError("The selected inventory options are not coherent.")
            if inventory.filter != 'lot' and inventory.lot_id:
                raise ValueError("The selected inventory options are not coherent.")
            if inventory.filter not in ('owner', 'product_owner') and inventory.partner_id:
                raise ValueError("The selected inventory options are not coherent.")
            if inventory.filter != 'pack' and inventory.package_id:
                raise ValueError("The selected inventory options are not coherent.")
        return True

    @api.onchange('filter')
    def onchange_filter(self):
        if self.filter not in ('product', 'product_owner'):
            self.product_id = False
        if self.filter != 'lot':
            self.lot = False
        if self.filter not in ('owner', 'product_owner'):
            self.partner_id = False
        if self.filter != 'pack':
            self.package_id = False
