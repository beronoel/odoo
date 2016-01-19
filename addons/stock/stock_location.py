# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api

#----------------------------------------------------------
# Stock Location
#----------------------------------------------------------
class StockLocation(models.Model):
    _name = "stock.location"
    _description = "Inventory Locations"
    _parent_name = "location_id"
    _parent_store = True
    _parent_order = 'name'
    _order = 'parent_left'
    _rec_name = 'complete_name'

    @api.model
    def _location_owner(self, location):
        ''' Return the company owning the location if any '''
        return location and (location.usage == 'internal') and location.company_id or False

    @api.multi
    def _complete_name(self):
        """ Forms complete name of location from parent location to child location.
        @return: Dictionary of values
        """
        for m in self:
            m.complete_name = m.name
            parent = m.location_id
            while parent:
                m.complete_name = parent.name + ' / ' + m.complete_name
                parent = parent.location_id

    @api.depends('name', 'location_id', 'active')
    def _get_sublocations(self):
        """ return all sublocations of the given stock locations (included) """
        return self.with_context(active_test=False).search([('id', 'child_of', self.ids)]).ids

    @api.model
    def _name_get(self, location):
        name = location.name
        while location.location_id and location.usage != 'view':
            location = location.location_id
            name = location.name + '/' + name
        return name

    @api.multi
    def name_get(self):
        res = []
        for location in self:
            res.append((location.id, self._name_get(location)))
        return res

    name = fields.Char('Location Name', required=True, translate=True)
    active = fields.Boolean(default=True, help="By unchecking the active field, you may hide a location without deleting it.")
    usage = fields.Selection([
                    ('supplier', 'Vendor Location'),
                    ('view', 'View'),
                    ('internal', 'Internal Location'),
                    ('customer', 'Customer Location'),
                    ('inventory', 'Inventory Loss'),
                    ('procurement', 'Procurement'),
                    ('production', 'Production'),
                    ('transit', 'Transit Location')],
            'Location Type', required=True, default='internal',
            help="""* Vendor Location: Virtual location representing the source location for products coming from your vendors
                   \n* View: Virtual location used to create a hierarchical structures for your warehouse, aggregating its child locations ; can't directly contain products
                   \n* Internal Location: Physical locations inside your own warehouses,
                   \n* Customer Location: Virtual location representing the destination location for products sent to your customers
                   \n* Inventory Loss: Virtual location serving as counterpart for inventory operations used to correct stock levels (Physical inventories)
                   \n* Procurement: Virtual location serving as temporary counterpart for procurement operations when the source (vendor or production) is not known yet. This location should be empty when the procurement scheduler has finished running.
                   \n* Production: Virtual counterpart location for production operations: this location consumes the raw material and produces finished products
                   \n* Transit Location: Counterpart location that should be used in inter-companies or inter-warehouses operations
                  """, select=True)
    complete_name = fields.Char(compute="_complete_name", string="Full Location Name")
    location_id = fields.Many2one('stock.location', 'Parent Location', select=True, ondelete='cascade')
    child_ids = fields.One2many('stock.location', 'location_id', 'Contains')

    partner_id = fields.Many2one('res.partner', 'Owner', help="Owner of the location if not internal")

    comment = fields.Text('Additional Information')
    posx = fields.Integer('Corridor (X)', default=0, help="Optional localization details, for information purpose only")
    posy = fields.Integer('Shelves (Y)', default=0, help="Optional localization details, for information purpose only")
    posz = fields.Integer('Height (Z)', default=0, help="Optional localization details, for information purpose only")

    parent_left = fields.Integer('Left Parent', select=1)
    parent_right = fields.Integer('Right Parent', select=1)

    company_id = fields.Many2one('res.company', 'Company', select=1, default=lambda self: self.env.user.company_id, help='Let this field empty if this location is shared between companies')
    scrap_location = fields.Boolean('Is a Scrap Location?', default=False, help='Check this box to allow using this location to put scrapped/damaged goods.')
    return_location = fields.Boolean('Is a Return Location?', help='Check this box to allow using this location as a return location.')
    removal_strategy_id = fields.Many2one('product.removal', 'Removal Strategy', help="Defines the default method used for suggesting the exact location (shelf) where to take the products from, which lot etc. for this location. This method can be enforced at the product category level, and a fallback is made on the parent locations if none is set here.")
    putaway_strategy_id = fields.Many2one('product.putaway', 'Put Away Strategy', help="Defines the default method used for suggesting the exact location (shelf) where to store the products. This method can be enforced at the product category level, and a fallback is made on the parent locations if none is set here.")
    barcode = fields.Char('Barcode', copy=False, oldname='loc_barcode')

    _sql_constraints = [('barcode_company_uniq', 'unique (barcode,company_id)', 'The barcode for a location must be unique per company !')]

    @api.model
    def create(self, default):
        if not default.get('barcode'):
            default.update({'barcode': default.get('complete_name')})
        return super(StockLocation, self).create(default)

    @api.model
    def get_putaway_strategy(self, location, product):
        ''' Returns the location where the product has to be put, if any compliant putaway strategy is found. Otherwise returns None.'''
        PutaWay = self.env['product.putaway']
        loc = location
        while loc:
            if loc.putaway_strategy_id:
                res = PutaWay.putaway_apply(loc.putaway_strategy_id, product)
                if res:
                    return res
            loc = loc.location_id

    @api.model
    def _default_removal_strategy(self):
        return 'fifo'

    @api.model
    def get_removal_strategy(self, qty, move, ops=False):
        ''' Returns the removal strategy to consider for the given move/ops
            :rtype: char
        '''
        product = move.product_id
        location = move.location_id
        if product.categ_id.removal_strategy_id:
            return product.categ_id.removal_strategy_id.method
        loc = location
        while loc:
            if loc.removal_strategy_id:
                return loc.removal_strategy_id.method
            loc = loc.location_id
        return self._default_removal_strategy()

    @api.model
    def get_warehouse(self, location):
        """
            Returns warehouse id of warehouse that contains location
            :param location: browse record (stock.location)
        """
        whs = self.env["stock.warehouse"].search([('view_location_id.parent_left', '<=', location.parent_left),
                                ('view_location_id.parent_right', '>=', location.parent_left)]).ids
        return whs and whs[0] or False
