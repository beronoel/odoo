# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.exceptions import UserError
from odoo import models, fields, api, _

#----------------------------------------------------------
# Stock Warehouse
#----------------------------------------------------------
class StockWarehouse(models.Model):
    _name = "stock.warehouse"
    _description = "Warehouse"

    name = fields.Char('Warehouse Name', required=True, select=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, readonly=True, select=True, default=lambda self: self.env.user.company_id)
    partner_id = fields.Many2one('res.partner', 'Address')
    view_location_id = fields.Many2one('stock.location', 'View Location', required=True, domain=[('usage', '=', 'view')])
    lot_stock_id = fields.Many2one('stock.location', 'Location Stock', domain=[('usage', '=', 'internal')], required=True)
    code = fields.Char('Short Name', size=5, required=True, help="Short name used to identify your warehouse")
    route_ids = fields.Many2many('stock.location.route', 'stock_route_warehouse', 'warehouse_id', 'route_id', 'Routes', domain="[('warehouse_selectable', '=', True)]", help='Defaults routes through the warehouse')
    reception_steps = fields.Selection([
        ('one_step', 'Receive goods directly in stock (1 step)'),
        ('two_steps', 'Unload in input location then go to stock (2 steps)'),
        ('three_steps', 'Unload in input location, go through a quality control before being admitted in stock (3 steps)')], 'Incoming Shipments',
        help="Default incoming route to follow", required=True, default='one_step')
    delivery_steps = fields.Selection([
        ('ship_only', 'Ship directly from stock (Ship only)'),
        ('pick_ship', 'Bring goods to output location before shipping (Pick + Ship)'),
        ('pick_pack_ship', 'Make packages into a dedicated location, then bring them to the output location for shipping (Pick + Pack + Ship)')], 'Outgoing Shippings',
        help="Default outgoing route to follow", required=True, default='ship_only')
    wh_input_stock_loc_id = fields.Many2one('stock.location', 'Input Location')
    wh_qc_stock_loc_id = fields.Many2one('stock.location', 'Quality Control Location')
    wh_output_stock_loc_id = fields.Many2one('stock.location', 'Output Location')
    wh_pack_stock_loc_id = fields.Many2one('stock.location', 'Packing Location')
    mto_pull_id = fields.Many2one('procurement.rule', 'MTO rule')
    pick_type_id = fields.Many2one('stock.picking.type', 'Pick Type')
    pack_type_id = fields.Many2one('stock.picking.type', 'Pack Type')
    out_type_id = fields.Many2one('stock.picking.type', 'Out Type')
    in_type_id = fields.Many2one('stock.picking.type', 'In Type')
    int_type_id = fields.Many2one('stock.picking.type', 'Internal Type')
    crossdock_route_id = fields.Many2one('stock.location.route', 'Crossdock Route')
    reception_route_id = fields.Many2one('stock.location.route', 'Receipt Route')
    delivery_route_id = fields.Many2one('stock.location.route', 'Delivery Route')
    resupply_from_wh = fields.Boolean('Resupply From Other Warehouses', help='Unused field')
    resupply_wh_ids = fields.Many2many('stock.warehouse', 'stock_wh_resupply_table', 'supplied_wh_id', 'supplier_wh_id', 'Resupply Warehouses')
    resupply_route_ids = fields.One2many('stock.location.route', 'supplied_wh_id', 'Resupply Routes',
        help="Routes will be created for these resupply warehouses and you can select them on products and product categories")
    default_resupply_wh_id = fields.Many2one('stock.warehouse', 'Default Resupply Warehouse', help="Goods will always be resupplied from this warehouse")

    @api.multi
    @api.onchange('default_resupply_wh_id', 'resupply_wh_ids')
    def onchange_filter_default_resupply_wh_id(self):
        resupply_wh_ids = set([x['id'] for x in (self.resolve_2many_commands('resupply_wh_ids', self.resupply_wh_ids, ['id']))])
        if self.default_resupply_wh_id:  # If we are removing the default resupply, we don't have default_resupply_wh_id
            resupply_wh_ids.add(self.default_resupply_wh_id.id)
        self.resupply_wh_ids = list(resupply_wh_ids)

    @api.multi
    def _get_external_transit_location(self):
        ''' returns browse record of inter company transit location, if found'''
        try:
            inter_wh_loc = self.env.ref('stock.stock_location_inter_wh')
        except:
            return False
        return inter_wh_loc

    @api.multi
    def _get_inter_wh_route(self, wh):
        return {
            'name': _('%s: Supply Product from %s') % (self.name, wh.name),
            'warehouse_selectable': False,
            'product_selectable': True,
            'product_categ_selectable': True,
            'supplied_wh_id': self.id,
            'supplier_wh_id': wh.id,
        }

    @api.multi
    def _create_resupply_routes(self, supplier_warehouses, default_resupply_wh):
        pull_obj = self.env['procurement.rule']
        # warehouse
        #create route selectable on the product to resupply the warehouse from another one
        external_transit_location = self._get_external_transit_location()
        internal_transit_location = self.company_id.internal_transit_location_id
        input_loc = self.wh_input_stock_loc_id
        if self.reception_steps == 'one_step':
            input_loc = self.lot_stock_id
        for wh in supplier_warehouses:
            transit_location = wh.company_id.id == self.company_id.id and internal_transit_location or external_transit_location
            if transit_location:
                output_loc = wh.wh_output_stock_loc_id
                if wh.delivery_steps == 'ship_only':
                    output_loc = wh.lot_stock_id
                    # Create extra MTO rule (only for 'ship only' because in the other cases MTO rules already exists)
                    mto_pull_vals = wh._get_mto_pull_rule([(output_loc, transit_location, wh.out_type_id.id)])[0]
                    pull_obj.create(mto_pull_vals)
                inter_wh_route_vals = self._get_inter_wh_route(wh)
                inter_wh_route_id = self.env['stock.location.route'].create(vals=inter_wh_route_vals)
                values = [(output_loc, transit_location, wh.out_type_id.id, wh), (transit_location, input_loc, self.in_type_id.id, self)]
                pull_rules_list = wh._get_supply_pull_rules(values, inter_wh_route_id)
                for pull_rule in pull_rules_list:
                    pull_obj.create(vals=pull_rule)
                #if the warehouse is also set as default resupply method, assign this route automatically to the warehouse
                if default_resupply_wh and default_resupply_wh.id == wh.id:
                    self.write({'route_ids': [(4, inter_wh_route_id.id)]})
                    wh.write({'route_ids': [(4, inter_wh_route_id.id)]})

    _sql_constraints = [
        ('warehouse_name_uniq', 'unique(name, company_id)', 'The name of the warehouse must be unique per company!'),
        ('warehouse_code_uniq', 'unique(code, company_id)', 'The code of the warehouse must be unique per company!'),
    ]

    @api.multi
    def _get_partner_locations(self):
        ''' returns a tuple made of the browse record of customer location and the browse record of supplier location'''
        location_obj = self.env['stock.location']
        try:
            customer_loc = self.env.ref('stock.stock_location_customers').id
            supplier_loc = self.env.ref('stock.stock_location_suppliers').id
        except:
            customer_loc = location_obj.search([('usage', '=', 'customer')]).ids
            customer_loc = customer_loc and customer_loc[0] or False
            supplier_loc = location_obj.search([('usage', '=', 'supplier')]).ids
            supplier_loc = supplier_loc and supplier_loc[0] or False
        if not (customer_loc and supplier_loc):
            raise UserError(_('Can\'t find any customer or supplier location.'))
        return location_obj.browse([customer_loc, supplier_loc])

    @api.model
    def _location_used(self, location_id):
        domain = ['&', ('route_id', 'not in', self.route_ids.ids),
                       '|', ('location_src_id', '=', location_id),                      # noqa
                            ('location_id', '=', location_id)
                  ]
        pulls = self.env['procurement.rule'].search_count(domain)

        domain = ['&', ('route_id', 'not in', self.route_ids.ids),
                       '|', ('location_from_id', '=', location_id),                     # noqa
                            ('location_dest_id', '=', location_id)
                  ]
        pushs = self.env['stock.location.path'].search_count(domain)
        if pulls or pushs:
            return True

    @api.multi
    def switch_location(self, new_reception_step=False, new_delivery_step=False):
        new_reception_step = new_reception_step or self.reception_steps
        new_delivery_step = new_delivery_step or self.delivery_steps
        if self.reception_steps != new_reception_step:
            if not self._location_used(self.wh_input_stock_loc_id.id):
                self.wh_input_stock_loc_id.write({'active': False})
                self.wh_qc_stock_loc_id.write({'active': False})
            if new_reception_step != 'one_step':
                self.wh_input_stock_loc_id.write({'active': True})
            if new_reception_step == 'three_steps':
                self.wh_qc_stock_loc_id.write({'active': True})

        if self.delivery_steps != new_delivery_step:
            if not self._location_used(self.wh_output_stock_loc_id.id):
                self.wh_output_stock_loc_id.write({'active': False})
            if not self._location_used(self.wh_pack_stock_loc_id.id):
                self.wh_pack_stock_loc_id.write({'active': False})
            if new_delivery_step != 'ship_only':
                self.wh_output_stock_loc_id.write({'active': True})
            if new_delivery_step == 'pick_pack_ship':
                self.wh_pack_stock_loc_id.write({'active': True})
        return True

    @api.model
    def _get_reception_delivery_route(self, route_name):
        return {
            'name': self._format_routename(route_name),
            'product_categ_selectable': True,
            'product_selectable': False,
            'sequence': 10,
        }

    @api.multi
    def _get_supply_pull_rules(self, values, new_route_id):
        pull_rules_list = []
        for from_loc, dest_loc, pick_type_id, warehouse in values:
            pull_rules_list.append({
                'name': warehouse._format_rulename(from_loc, dest_loc),
                'location_src_id': from_loc.id,
                'location_id': dest_loc.id,
                'route_id': new_route_id.id,
                'action': 'move',
                'picking_type_id': pick_type_id,
                'procure_method': warehouse.lot_stock_id.id != from_loc.id and 'make_to_order' or 'make_to_stock',  # first part of the resuply route is MTS
                'warehouse_id': warehouse.id,
                'propagate_warehouse_id': self.id,
            })
        return pull_rules_list

    @api.multi
    def _get_push_pull_rules(self, active, values, new_route_id):
        first_rule = True
        push_rules_list = []
        pull_rules_list = []
        for from_loc, dest_loc, pick_type_id in values:
            push_rules_list.append({
                'name': self._format_rulename(from_loc, dest_loc),
                'location_from_id': from_loc.id,
                'location_dest_id': dest_loc.id,
                'route_id': new_route_id.id,
                'auto': 'manual',
                'picking_type_id': pick_type_id,
                'active': active,
                'warehouse_id': self.id,
            })
            pull_rules_list.append({
                'name': self._format_rulename(from_loc, dest_loc),
                'location_src_id': from_loc.id,
                'location_id': dest_loc.id,
                'route_id': new_route_id.id,
                'action': 'move',
                'picking_type_id': pick_type_id,
                'procure_method': first_rule is True and 'make_to_stock' or 'make_to_order',
                'active': active,
                'warehouse_id': self.id,
            })
            first_rule = False
        return push_rules_list, pull_rules_list

    @api.model
    def _get_mto_route(self):
        try:
            mto_route_id = self.env.ref('stock.route_warehouse0_mto').id
        except:
            mto_route_id = self.env['stock.location.route'].search([('name', 'like', _('Make To Order'))]).ids
            mto_route_id = mto_route_id and mto_route_id[0] or False
        if not mto_route_id:
            raise UserError(_('Can\'t find any generic Make To Order route.'))
        return mto_route_id

    @api.multi
    def _check_remove_mto_resupply_rules(self):
        """ Checks that the moves from the different """
        mto_route_id = self._get_mto_route()
        rules = self.env['procurement.rule'].search(['&', ('location_src_id', '=', self.lot_stock_id.id), ('location_id.usage', '=', 'transit')])
        rules.unlink()

    @api.multi
    def _get_mto_pull_rule(self, values):
        mto_route_id = self._get_mto_route()
        res = []
        for value in values:
            from_loc, dest_loc, pick_type_id = value
            res += [{
                'name': self._format_rulename(from_loc, dest_loc) + _(' MTO'),
                'location_src_id': from_loc.id,
                'location_id': dest_loc.id,
                'route_id': mto_route_id,
                'action': 'move',
                'picking_type_id': pick_type_id,
                'procure_method': 'make_to_order',
                'active': True,
                'warehouse_id': self.id,
            }]
        return res

    @api.model
    def _get_crossdock_route(self, route_name):
        return {
            'name': self._format_routename(route_name),
            'warehouse_selectable': False,
            'product_selectable': True,
            'product_categ_selectable': True,
            'active': self.delivery_steps != 'ship_only' and self.reception_steps != 'one_step',
            'sequence': 20,
        }

    # TO Do: FIX purchase and mrp module
    @api.multi
    def create_routes(self, warehouse):
        wh_route_ids = []
        route_obj = self.env['stock.location.route']
        pull_obj = self.env['procurement.rule']
        push_obj = self.env['stock.location.path']
        routes_dict = self.get_routes_dict()
        #create reception route and rules
        route_name, values = routes_dict[warehouse.reception_steps]
        route_vals = warehouse._get_reception_delivery_route(route_name)
        reception_route_id = route_obj.create(route_vals)
        wh_route_ids.append((4, reception_route_id.id))
        push_rules_list, pull_rules_list = warehouse._get_push_pull_rules(True, values, reception_route_id)
        #create the push/procurement rules
        for push_rule in push_rules_list:
            push_obj.create(vals=push_rule)
        for pull_rule in pull_rules_list:
            #all procurement rules in reception route are mto, because we don't want to wait for the scheduler to trigger an orderpoint on input location
            pull_rule['procure_method'] = 'make_to_order'
            pull_obj.create(vals=pull_rule)

        #create MTS route and procurement rules for delivery and a specific route MTO to be set on the product
        route_name, values = routes_dict[warehouse.delivery_steps]
        route_vals = warehouse._get_reception_delivery_route(route_name)
        #create the route and its procurement rules
        delivery_route_id = route_obj.create(route_vals)
        wh_route_ids.append((4, delivery_route_id.id))
        dummy, pull_rules_list = warehouse._get_push_pull_rules(True, values, delivery_route_id)
        for pull_rule in pull_rules_list:
            pull_obj.create(vals=pull_rule)
        #create MTO procurement rule and link it to the generic MTO route
        mto_pull_vals = warehouse._get_mto_pull_rule(values)[0]
        mto_pull_id = pull_obj.create(mto_pull_vals)

        #create a route for cross dock operations, that can be set on products and product categories
        route_name, values = routes_dict['crossdock']
        crossdock_route_vals = warehouse._get_crossdock_route(route_name)
        crossdock_route_id = route_obj.create(vals=crossdock_route_vals)
        wh_route_ids.append((4, crossdock_route_id.id))
        dummy, pull_rules_list = warehouse._get_push_pull_rules(warehouse.delivery_steps != 'ship_only' and warehouse.reception_steps != 'one_step', values, crossdock_route_id)
        for pull_rule in pull_rules_list:
            # Fixed cross-dock is logically mto
            pull_rule['procure_method'] = 'make_to_order'
            pull_obj.create(vals=pull_rule)

        #create route selectable on the product to resupply the warehouse from another one
        warehouse._create_resupply_routes(warehouse.resupply_wh_ids, warehouse.default_resupply_wh_id)

        #return routes and mto procurement rule to store on the warehouse
        return {
            'route_ids': wh_route_ids,
            'mto_pull_id': mto_pull_id.id,
            'reception_route_id': reception_route_id.id,
            'delivery_route_id': delivery_route_id.id,
            'crossdock_route_id': crossdock_route_id.id,
        }

    @api.multi
    def change_route(self, new_reception_step=False, new_delivery_step=False):
        pull_obj = self.env['procurement.rule']
        push_obj = self.env['stock.location.path']
        new_reception_step = new_reception_step or self.reception_steps
        new_delivery_step = new_delivery_step or self.delivery_steps

        #change the default source and destination location and (de)activate picking types
        input_loc = self.wh_input_stock_loc_id
        if new_reception_step == 'one_step':
            input_loc = self.lot_stock_id
        output_loc = self.wh_output_stock_loc_id
        if new_delivery_step == 'ship_only':
            output_loc = self.lot_stock_id
        self.in_type_id.write({'default_location_dest_id': input_loc.id})
        self.out_type_id.write({'default_location_src_id': output_loc.id})
        self.pick_type_id.write({
                'active': new_delivery_step != 'ship_only',
                'default_location_dest_id': output_loc.id if new_delivery_step == 'pick_ship' else self.wh_pack_stock_loc_id.id,
            })
        self.pack_type_id.write({'active': new_delivery_step == 'pick_pack_ship'})

        routes_dict = self.get_routes_dict()
        #update delivery route and rules: unlink the existing rules of the warehouse delivery route and recreate it
        self.delivery_route_id.pull_ids.unlink()
        route_name, values = routes_dict[new_delivery_step]
        self.delivery_route_id.write({'name': self._format_routename(route_name)})
        dummy, pull_rules_list = self._get_push_pull_rules(True, values, self.delivery_route_id)
        #create the procurement rules
        for pull_rule in pull_rules_list:
            pull_obj.create(vals=pull_rule)

        #update receipt route and rules: unlink the existing rules of the warehouse receipt route and recreate it
        self.reception_route_id.pull_ids.unlink()
        self.reception_route_id.push_ids.unlink()
        route_name, values = routes_dict[new_reception_step]
        self.reception_route_id.write({'name': self._format_routename(route_name)})
        push_rules_list, pull_rules_list = self._get_push_pull_rules(True, values, self.reception_route_id)
        #create the push/procurement rules
        for push_rule in push_rules_list:
            push_obj.create(vals=push_rule)
        for pull_rule in pull_rules_list:
            #all procurement rules in receipt route are mto, because we don't want to wait for the scheduler to trigger an orderpoint on input location
            pull_rule['procure_method'] = 'make_to_order'
            pull_obj.create(vals=pull_rule)

        self.crossdock_route_id.write({'active': new_reception_step != 'one_step' and new_delivery_step != 'ship_only'})

        #change MTO rule
        dummy, values = routes_dict[new_delivery_step]
        mto_pull_vals = self._get_mto_pull_rule(values)[0]
        self.mto_pull_id.write(mto_pull_vals)
        return True

    @api.multi
    def create_sequences_and_picking_types(self):
        seq_obj = self.env['ir.sequence']
        picking_type_obj = self.env['stock.picking.type']
        #create new sequences
        in_seq_id = seq_obj.sudo().create({'name': self.name + _(' Sequence in'), 'prefix': self.code + '/IN/', 'padding': 5})
        out_seq_id = seq_obj.sudo().create({'name': self.name + _(' Sequence out'), 'prefix': self.code + '/OUT/', 'padding': 5})
        pack_seq_id = seq_obj.sudo().create({'name': self.name + _(' Sequence packing'), 'prefix': self.code + '/PACK/', 'padding': 5})
        pick_seq_id = seq_obj.sudo().create({'name': self.name + _(' Sequence picking'), 'prefix': self.code + '/PICK/', 'padding': 5})
        int_seq_id = seq_obj.sudo().create({'name': self.name + _(' Sequence internal'), 'prefix': self.code + '/INT/', 'padding': 5})

        wh_stock_loc = self.lot_stock_id
        wh_input_stock_loc = self.wh_input_stock_loc_id
        wh_output_stock_loc = self.wh_output_stock_loc_id
        wh_pack_stock_loc = self.wh_pack_stock_loc_id

        #create in, out, internal picking types for warehouse
        input_loc = wh_input_stock_loc
        if self.reception_steps == 'one_step':
            input_loc = wh_stock_loc
        output_loc = wh_output_stock_loc
        if self.delivery_steps == 'ship_only':
            output_loc = wh_stock_loc

        #choose the next available color for the picking types of this warehouse
        color = 0
        available_colors = [0, 3, 4, 5, 6, 7, 8, 1, 2]  # put white color first
        all_used_colors = self.env['stock.picking.type'].search_read([('warehouse_id', '!=', False), ('color', '!=', False)], ['color'], order='color')
        #don't use sets to preserve the list order
        for x in all_used_colors:
            if x['color'] in available_colors:
                available_colors.remove(x['color'])
        if available_colors:
            color = available_colors[0]

        #order the picking types with a sequence allowing to have the following suit for each warehouse: reception, internal, pick, pack, ship.
        max_sequence = self.env['stock.picking.type'].search_read([], ['sequence'], order='sequence desc')
        max_sequence = max_sequence and max_sequence[0]['sequence'] or 0
        internal_active_false = (self.reception_steps == 'one_step') and (self.delivery_steps == 'ship_only')
        internal_active_false = internal_active_false and not self.user_has_groups('stock.group_locations')

        in_type_id = picking_type_obj.create(vals={
            'name': _('Receipts'),
            'warehouse_id': self.id,
            'code': 'incoming',
            'use_create_lots': True,
            'use_existing_lots': False,
            'sequence_id': in_seq_id.id,
            'default_location_src_id': False,
            'default_location_dest_id': input_loc.id,
            'sequence': max_sequence + 1,
            'color': color})
        out_type_id = picking_type_obj.create(vals={
            'name': _('Delivery Orders'),
            'warehouse_id': self.id,
            'code': 'outgoing',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': out_seq_id.id,
            'return_picking_type_id': in_type_id.id,
            'default_location_src_id': output_loc.id,
            'default_location_dest_id': False,
            'sequence': max_sequence + 4,
            'color': color})
        in_type_id.write({'return_picking_type_id': out_type_id.id})
        int_type_id = picking_type_obj.create(vals={
            'name': _('Internal Transfers'),
            'warehouse_id': self.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': int_seq_id.id,
            'default_location_src_id': wh_stock_loc.id,
            'default_location_dest_id': wh_stock_loc.id,
            'active': not internal_active_false,
            'sequence': max_sequence + 2,
            'color': color})
        pack_type_id = picking_type_obj.create(vals={
            'name': _('Pack'),
            'warehouse_id': self.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': pack_seq_id.id,
            'default_location_src_id': wh_pack_stock_loc.id,
            'default_location_dest_id': output_loc.id,
            'active': self.delivery_steps == 'pick_pack_ship',
            'sequence': max_sequence + 3,
            'color': color})
        pick_type_id = picking_type_obj.create(vals={
            'name': _('Pick'),
            'warehouse_id': self.id,
            'code': 'internal',
            'use_create_lots': False,
            'use_existing_lots': True,
            'sequence_id': pick_seq_id.id,
            'default_location_src_id': wh_stock_loc.id,
            'default_location_dest_id': output_loc.id if self.delivery_steps == 'pick_ship' else wh_pack_stock_loc.id,
            'active': self.delivery_steps != 'ship_only',
            'sequence': max_sequence + 2,
            'color': color})

        #write picking types on WH
        vals = {
            'in_type_id': in_type_id.id,
            'out_type_id': out_type_id.id,
            'pack_type_id': pack_type_id.id,
            'pick_type_id': pick_type_id.id,
            'int_type_id': int_type_id.id,
        }
        super(StockWarehouse, self).write(vals=vals)

    @api.model
    def create(self, vals):
        if vals is None:
            vals = {}
        # seq_obj = self.pool.get('ir.sequence')
        # picking_type_obj = self.pool.get('stock.picking.type')
        location_obj = self.env['stock.location']

        #create view location for warehouse
        loc_vals = {
                'name': _(vals.get('code')),
                'usage': 'view',
                'location_id': self.env.ref('stock.stock_location_locations').id,
        }
        if vals.get('company_id'):
            loc_vals['company_id'] = vals.get('company_id')
        wh_loc_id = location_obj.create(loc_vals)
        vals['view_location_id'] = wh_loc_id.id
        #create all location
        def_values = self.default_get({'reception_steps', 'delivery_steps'})
        reception_steps = vals.get('reception_steps',  def_values['reception_steps'])
        delivery_steps = vals.get('delivery_steps', def_values['delivery_steps'])
        # context_with_inactive = context.copy()
        # context_with_inactive['active_test'] = False
        sub_locations = [
            {'name': _('Stock'), 'active': True, 'field': 'lot_stock_id'},
            {'name': _('Input'), 'active': reception_steps != 'one_step', 'field': 'wh_input_stock_loc_id'},
            {'name': _('Quality Control'), 'active': reception_steps == 'three_steps', 'field': 'wh_qc_stock_loc_id'},
            {'name': _('Output'), 'active': delivery_steps != 'ship_only', 'field': 'wh_output_stock_loc_id'},
            {'name': _('Packing Zone'), 'active': delivery_steps == 'pick_pack_ship', 'field': 'wh_pack_stock_loc_id'},
        ]
        for values in sub_locations:
            loc_vals = {
                'name': values['name'],
                'usage': 'internal',
                'location_id': wh_loc_id.id,
                'active': values['active'],
            }
            if vals.get('company_id'):
                loc_vals['company_id'] = vals.get('company_id')
            location_id = location_obj.with_context(active_test=False).create(loc_vals)
            vals[values['field']] = location_id.id

        #create WH
        new_id = super(StockWarehouse, self).create(vals=vals)
        # warehouse = new_id
        new_id.create_sequences_and_picking_types()

        #create routes and push/procurement rules
        # TO Do: sale, purchase module
        new_objects_dict = new_id.create_routes(new_id)
        new_id.write(new_objects_dict)

        # If partner assigned
        if vals.get('partner_id'):
            comp_obj = self.env['res.company']
            if vals.get('company_id'):
                transit_loc = comp_obj.browse(vals.get('company_id')).internal_transit_location_id.id
            else:
                # transit_loc = comp_obj.browse(comp_obj._company_default_get('stock.warehouse')).internal_transit_location_id.id
                transit_loc = comp_obj._company_default_get('stock.warehouse').internal_transit_location_id.id
            self.env['res.partner'].browse([vals['partner_id']]).write({'property_stock_customer': transit_loc, 'property_stock_supplier': transit_loc})
        return new_id

    @api.multi
    def _format_rulename(self, from_loc, dest_loc):
        return self.code + ': ' + from_loc.name + ' -> ' + dest_loc.name

    # To Do: mrp fix.
    @api.v7
    def _format_routename(self, cr, uid, obj, name, context=None):
        return obj.name + ': ' + name

    @api.v8
    def _format_routename(self, name):
        return self.name + ': ' + name

    @api.multi
    def get_routes_dict(self):
        #fetch customer and supplier locations, for references
        customer_loc, supplier_loc = self._get_partner_locations()

        return {
            'one_step': (_('Receipt in 1 step'), []),
            'two_steps': (_('Receipt in 2 steps'), [(self.wh_input_stock_loc_id, self.lot_stock_id, self.int_type_id.id)]),
            'three_steps': (_('Receipt in 3 steps'), [(self.wh_input_stock_loc_id, self.wh_qc_stock_loc_id, self.int_type_id.id), (self.wh_qc_stock_loc_id, self.lot_stock_id, self.int_type_id.id)]),
            'crossdock': (_('Cross-Dock'), [(self.wh_input_stock_loc_id, self.wh_output_stock_loc_id, self.int_type_id.id), (self.wh_output_stock_loc_id, customer_loc, self.out_type_id.id)]),
            'ship_only': (_('Ship Only'), [(self.lot_stock_id, customer_loc, self.out_type_id.id)]),
            'pick_ship': (_('Pick + Ship'), [(self.lot_stock_id, self.wh_output_stock_loc_id, self.pick_type_id.id), (self.wh_output_stock_loc_id, customer_loc, self.out_type_id.id)]),
            'pick_pack_ship': (_('Pick + Pack + Ship'), [(self.lot_stock_id, self.wh_pack_stock_loc_id, self.pick_type_id.id), (self.wh_pack_stock_loc_id, self.wh_output_stock_loc_id, self.pack_type_id.id), (self.wh_output_stock_loc_id, customer_loc, self.out_type_id.id)]),
        }

    @api.multi
    def _handle_renaming(self, name, code):
        #rename location
        # location_id = self.lot_stock_id.location_id.id
        self.lot_stock_id.location_id.write({'name': code})
        #rename route and push-procurement rules
        for route in self.route_ids:
            route.write({'name': route.name.replace(self.name, name, 1)})
            for pull in route.pull_ids:
                pull.write({'name': pull.name.replace(self.name, name, 1)})
            for push in route.push_ids:
                push.write({'name': pull.name.replace(self.name, name, 1)})
        #change the mto procurement rule name
        if self.mto_pull_id.id:
            self.mto_pull_id.write({'name': self.mto_pull_id.name.replace(self.name, name, 1)})

    @api.multi
    def _check_delivery_resupply(self, new_location, change_to_multiple):
        """ Will check if the resupply routes from this warehouse follow the changes of number of delivery steps """
        #Check routes that are being delivered by this warehouse and change the rule going to transit location
        pull_obj = self.env["procurement.rule"]
        routes = self.env["stock.location.route"].search([('supplier_wh_id', '=', self.id)])
        pulls = pull_obj.search(['&', ('route_id', 'in', routes), ('location_id.usage', '=', 'transit')])
        if pulls:
            pulls.write({'location_src_id': new_location, 'procure_method': change_to_multiple and "make_to_order" or "make_to_stock"})
        # Create or clean MTO rules
        mto_route_id = self._get_mto_route()
        if not change_to_multiple:
            # If single delivery we should create the necessary MTO rules for the resupply
            # pulls = pull_obj.search(cr, uid, ['&', ('route_id', '=', mto_route_id), ('location_id.usage', '=', 'transit'), ('location_src_id', '=', warehouse.lot_stock_id.id)], context=context)
            # pull_recs = pulls
            # transfer_locs = list(set([x.location_id for x in pull_recs]))
            vals = [(self.lot_stock_id, x, self.out_type_id.id) for x in pulls.location_id.ids]
            mto_pull_vals = self._get_mto_pull_rule(vals)
            for mto_pull_val in mto_pull_vals:
                pull_obj.create(mto_pull_val)
        else:
            # We need to delete all the MTO procurement rules, otherwise they risk to be used in the system
            pulls = pull_obj.search(['&', ('route_id', '=', mto_route_id), ('location_id.usage', '=', 'transit'), ('location_src_id', '=', self.lot_stock_id.id)])
            if pulls:
                pulls.unlink()

    @api.multi
    def _check_reception_resupply(self, new_location):
        """
            Will check if the resupply routes to this warehouse follow the changes of number of receipt steps
        """
        #Check routes that are being delivered by this warehouse and change the rule coming from transit location
        routes = self.env["stock.location.route"].search([('supplied_wh_id', '=', self.id)])
        pulls = self.env["procurement.rule"].search(['&', ('route_id', 'in', routes), ('location_src_id.usage', '=', 'transit')])
        if pulls:
            pulls.write({'location_id': new_location})

    @api.multi
    def _check_resupply(self, reception_new, delivery_new):
        if reception_new:
            old_val = self.reception_steps
            new_val = reception_new
            change_to_one = (old_val != 'one_step' and new_val == 'one_step')
            change_to_multiple = (old_val == 'one_step' and new_val != 'one_step')
            if change_to_one or change_to_multiple:
                new_location = change_to_one and self.lot_stock_id.id or self.wh_input_stock_loc_id.id
                self._check_reception_resupply(new_location)
        if delivery_new:
            old_val = self.delivery_steps
            new_val = delivery_new
            change_to_one = (old_val != 'ship_only' and new_val == 'ship_only')
            change_to_multiple = (old_val == 'ship_only' and new_val != 'ship_only')
            if change_to_one or change_to_multiple:
                new_location = change_to_one and self.lot_stock_id.id or self.wh_output_stock_loc_id.id
                self._check_delivery_resupply(new_location, change_to_multiple)

    @api.multi
    def write(self, vals):
        route_obj = self.env['stock.location.route']
        # seq_obj = self.pool.get('ir.sequence')
        # route_obj = self.pool.get('stock.location.route')
        # context_with_inactive = context.copy()
        # context_with_inactive['active_test'] = False
        # self.with_context(active_test=False)
        for warehouse in self.with_context(active_test=False):
            #first of all, check if we need to delete and recreate route
            if vals.get('reception_steps') or vals.get('delivery_steps'):
                #activate and deactivate location according to reception and delivery option
                warehouse.switch_location(vals.get('reception_steps', False), vals.get('delivery_steps', False))
                # switch between route
                warehouse.with_context(active_test=False).change_route(vals.get('reception_steps', False), vals.get('delivery_steps', False))
                # Check if we need to change something to resupply warehouses and associated MTO rules
                warehouse._check_resupply(vals.get('reception_steps'), vals.get('delivery_steps'))
            if vals.get('code') or vals.get('name'):
                name = warehouse.name
                #rename sequence
                if vals.get('name'):
                    name = vals.get('name', warehouse.name)
                warehouse.with_context(active_test=False)._handle_renaming(name, vals.get('code', warehouse.code))
                if warehouse.in_type_id:
                    warehouse.in_type_id.sequence_id.write({'name': name + _(' Sequence in'), 'prefix': vals.get('code', warehouse.code) + '\IN\\'})
                if warehouse.out_type_id:
                    warehouse.in_type_id.sequence_id.write({'name': name + _(' Sequence out'), 'prefix': vals.get('code', warehouse.code) + '\OUT\\'})
                if warehouse.pack_type_id:
                    warehouse.pack_type_id.sequence_id.write({'name': name + _(' Sequence packing'), 'prefix': vals.get('code', warehouse.code) + '\PACK\\'})
                if warehouse.pick_type_id:
                    warehouse.pick_type_id.sequence_id.write({'name': name + _(' Sequence picking'), 'prefix': vals.get('code', warehouse.code) + '\PICK\\'})
                if warehouse.int_type_id:
                    warehouse.int_type_id.sequence_id.write({'name': name + _(' Sequence internal'), 'prefix': vals.get('code', warehouse.code) + '\INT\\'})
        if vals.get('resupply_wh_ids') and not vals.get('resupply_route_ids'):
            for cmd in vals.get('resupply_wh_ids'):
                if cmd[0] == 6:
                    new_ids = set(cmd[2])
                    old_ids = set([wh.id for wh in warehouse.resupply_wh_ids])
                    to_add_wh_ids = new_ids - old_ids
                    if to_add_wh_ids:
                        supplier_warehouses = self.browse(list(to_add_wh_ids))
                        warehouse._create_resupply_routes(supplier_warehouses, warehouse.default_resupply_wh_id)
                    to_remove_wh_ids = old_ids - new_ids
                    if to_remove_wh_ids:
                        to_remove_route_ids = route_obj.search([('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', 'in', list(to_remove_wh_ids))])
                        if to_remove_route_ids:
                            to_remove_route_ids.unlink()
                else:
                    #not implemented
                    pass
        if 'default_resupply_wh_id' in vals:
            if vals.get('default_resupply_wh_id') == warehouse.id:
                raise UserError(_('The default resupply warehouse should be different than the warehouse itself!'))
            if warehouse.default_resupply_wh_id:
                #remove the existing resupplying route on the warehouse
                to_remove_route_ids = route_obj.search([('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', '=', warehouse.default_resupply_wh_id.id)]).ids
                for inter_wh_route_id in to_remove_route_ids:
                    warehouse.write({'route_ids': [(3, inter_wh_route_id)]})
            if vals.get('default_resupply_wh_id'):
                #assign the new resupplying route on all products
                to_assign_route_ids = route_obj.search([('supplied_wh_id', '=', warehouse.id), ('supplier_wh_id', '=', vals.get('default_resupply_wh_id'))]).ids
                for inter_wh_route_id in to_assign_route_ids:
                    warehouse.write({'route_ids': [(4, inter_wh_route_id)]})

        # If another partner assigned
        if vals.get('partner_id'):
            if not vals.get('company_id'):
                company = self.env.user.company_id
            else:
                company = self.env['res.company'].browse(vals['company_id'])
            transit_loc = company.internal_transit_location_id.id
            self.env['res.partner'].browse([vals['partner_id']]).write({'property_stock_customer': transit_loc, 'property_stock_supplier': transit_loc})
        return super(StockWarehouse, self).write(vals=vals)

    @api.multi
    def get_all_routes_for_wh(self):
        route_obj = self.env["stock.location.route"]
        all_routes = [route.id for route in self.route_ids]
        all_routes += route_obj.search([('supplied_wh_id', '=', self.id)])
        all_routes += [self.mto_pull_id.route_id.id]
        return all_routes

    @api.multi
    def view_all_routes_for_wh(self):
        all_routes = []
        for wh in self:
            all_routes += wh.get_all_routes_for_wh()

        domain = [('id', 'in', all_routes)]
        return {
            'name': _('Warehouse\'s Routes'),
            'domain': domain,
            'res_model': 'stock.location.route',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'tree,form',
            'view_type': 'form',
            'limit': 20
        }
