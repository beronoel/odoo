# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time

from openerp.tools.float_utils import float_compare
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.addons.procurement import procurement

#----------------------------------------------------------
# Stock Picking
#----------------------------------------------------------

class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ['mail.thread']
    _description = "Transfer"
    _order = "priority desc, date asc, id desc"

    def _set_min_date(self):
        move_ids = self.mapped('move_lines')
        move_ids.write({'date_expected': self.min_date})

    def _set_priority(self):
        move_ids = self.mapped('move_lines')
        move_ids.write({'priority': self.priority})

    @api.multi
    def get_min_max_date(self):
        """ Finds minimum and maximum dates for picking.
        @return: Dictionary of values
        """
        if self:
            self.env.cr.execute("""select
                    picking_id,
                    min(date_expected),
                    max(date_expected),
                    max(priority)
                from
                    stock_move
                where
                    picking_id IN %s
                group by
                    picking_id""", (tuple(self.ids),))
            for pick, dt1, dt2, prio in self.env.cr.fetchall():
                StockPick = self.browse(pick)
                StockPick.min_date = dt1
                StockPick.max_date = dt2
                StockPick.priority = prio
        else:
            self.min_date = False
            self.max_date = False
            self.priority = '1'

    @api.model
    def create(self, vals):
        if ('name' not in vals) or (vals.get('name') in ('/', False)):
            ptype_id = vals.get('picking_type_id', self.env.context.get('default_picking_type_id', False))
            sequence_id = self.env['stock.picking.type'].browse(ptype_id).sequence_id
            vals['name'] = sequence_id.next_by_id()
        # As the on_change in one2many list is WIP, we will overwrite the locations on the stock moves here
        # As it is a create the format will be a list of (0, 0, dict)
        if vals.get('move_lines') and vals.get('location_id') and vals.get('location_dest_id'):
            for move in vals['move_lines']:
                if len(move) == 3:
                    move[2]['location_id'] = vals['location_id']
                    move[2]['location_dest_id'] = vals['location_dest_id']
        return super(StockPicking, self).create(vals)

    @api.multi
    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        after_vals = {}
        if vals.get('location_id'):
            after_vals['location_id'] = vals['location_id']
        if vals.get('location_dest_id'):
            after_vals['location_dest_id'] = vals['location_dest_id']
        # Change locations of moves if those of the picking change
        if after_vals:
            moves = []
            for pick in self:
                moves += [x.id for x in pick.move_lines if not x.scrapped]
            if moves:
                self.env['stock.move'].browse(moves).write(after_vals)
        return res

    @api.depends('move_lines.priority', 'move_lines.picking_id', 'move_lines.date_expected')
    def _get_pickings_dates_priority(self):
        res = set()
        for move in self:
            if move.picking_id and (not (move.picking_id.min_date < move.date_expected < move.picking_id.max_date) or move.priority > move.picking_id.priority):
                res.add(move.picking_id.id)
        return list(res)

    @api.multi
    def _get_pack_operation_exist(self):
        for pick in self:
            pick.pack_operation_exist = False
            if pick.pack_operation_ids:
                pick.pack_operation_exist = True

    @api.multi
    def _get_quant_reserved_exist(self):
        for pick in self:
            pick.quant_reserved_exist = False
            for move in pick.move_lines:
                if move.reserved_quant_ids:
                    pick.quant_reserved_exist = True
                    continue

    @api.multi
    def action_assign_owner(self):
        for picking in self:
            picking.pack_operation_ids.write({'owner_id': picking.owner_id.id})

    @api.depends('move_lines.state', 'move_lines.partially_available', 'move_lines.group_id', 'move_lines.picking_id')
    def _get_pickings(self):
        res = set()
        for move in self:
            if move.picking_id:
                res.add(move.picking_id.id)
        return list(res)

    @api.depends('move_type', 'launch_pack_operations', 'move_lines', 'move_lines.state', 'move_lines.partially_available', 'move_lines.picking_id')
    def _state_get(self):
        '''The state of a picking depends on the state of its related stock.move
            draft: the picking has no line or any one of the lines is draft
            done, draft, cancel: all lines are done / draft / cancel
            confirmed, waiting, assigned, partially_available depends on move_type (all at once or partial)
        '''
        for pick in self:
            if not pick.move_lines:
                pick.state = pick.launch_pack_operations and 'assigned' or 'draft'
                continue
            if any([x.state == 'draft' for x in pick.move_lines]):
                pick.state = 'draft'
                continue
            if all([x.state == 'cancel' for x in pick.move_lines]):
                pick.state = 'cancel'
                continue
            if all([x.state in ('cancel', 'done') for x in pick.move_lines]):
                pick.state = 'done'
                continue

            # new record of move_line not set state.
            if any([x.state for x in pick.move_lines]):
                order = {'confirmed': 0, 'waiting': 1, 'assigned': 2}
                order_inv = {0: 'confirmed', 1: 'waiting', 2: 'assigned'}
                lst = [order[x.state] for x in pick.move_lines if x.state not in ('cancel', 'done')]
                if pick.move_type == 'one':
                    pick.state = order_inv[min(lst)]
                else:
                    #we are in the case of partial delivery, so if all move are assigned, picking
                    #should be assign too, else if one of the move is assigned, or partially available, picking should be
                    #in partially available state, otherwise, picking is in waiting or confirmed state
                    pick.state = order_inv[max(lst)]
                    if not all(x == 2 for x in lst):
                        if any(x == 2 for x in lst):
                            pick.state = 'partially_available'
                        else:
                            #if all moves aren't assigned, check if we have one product partially available
                            for move in pick.move_lines:
                                if move.partially_available:
                                    pick.state = 'partially_available'
                                    break

    @api.onchange('partner_id', 'picking_type_id')
    def onchange_picking_type(self):
        if self.picking_type_id:
            picking_type = self.picking_type_id
            if not picking_type.default_location_src_id:
                if self.partner_id:
                    partner = self.partner_id
                    location_id = partner.property_stock_supplier.id
                else:
                    customerloc, supplierloc = self.env['stock.warehouse']._get_partner_locations()
                    location_id = supplierloc.id
            else:
                location_id = picking_type.default_location_src_id.id

            if not picking_type.default_location_dest_id:
                if self.partner_id:
                    partner = self.partner_id
                    location_dest_id = partner.property_stock_customer.id
                else:
                    customerloc, supplierloc = self.env['stock.warehouse']._get_partner_locations()
                    location_dest_id = customerloc.id
            else:
                location_dest_id = picking_type.default_location_dest_id.id

            self.location_id = location_id
            self.location_dest_id = location_dest_id

    def _default_location_destination(self):
        # retrieve picking type from context; if none this returns an empty recordset
        picking_type_id = self.env.context.get('default_picking_type_id')
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        return picking_type.default_location_dest_id

    def _default_location_source(self):
        # retrieve picking type from context; if none this returns an empty recordset
        picking_type_id = self.env.context.get('default_picking_type_id')
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        return picking_type.default_location_src_id

    def _search_min_dates(self, operator, value):
        pass

    name = fields.Char('Reference', select=True, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, copy=False, default='/')
    origin = fields.Char('Source Document', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, help="Reference of the document", select=True)
    backorder_id = fields.Many2one('stock.picking', 'Back Order of', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, help="If this shipment was split, then this field links to the shipment which contains the already processed part.", select=True, copy=False)
    note = fields.Text('Notes')
    move_type = fields.Selection([('direct', 'Partial'), ('one', 'All at once')], 'Delivery Method', required=True, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, help="It specifies goods to be deliver partially or all at once", default='direct')

    state = fields.Selection(compute="_state_get", copy=False, store=True,
        selection=[
            ('draft', 'Draft'),
            ('cancel', 'Cancelled'),
            ('waiting', 'Waiting Another Operation'),
            ('confirmed', 'Waiting Availability'),
            ('partially_available', 'Partially Available'),
            ('assigned', 'Available'),
            ('done', 'Done'),
            ], string='Status', readonly=True, select=True, track_visibility='onchange',
        help="""
            * Draft: not confirmed yet and will not be scheduled until confirmed\n
            * Waiting Another Operation: waiting for another move to proceed before it becomes automatically available (e.g. in Make-To-Order flows)\n
            * Waiting Availability: still waiting for the availability of products\n
            * Partially Available: some products are available and reserved\n
            * Ready to Transfer: products reserved, simply waiting for confirmation.\n
            * Transferred: has been processed, can't be modified or cancelled anymore\n
            * Cancelled: has been cancelled, can't be confirmed anymore""", defaul="draft"
    )
    location_id = fields.Many2one('stock.location', required=True, string="Source Location Zone",
                                      default=_default_location_source, readonly=True, states={'draft': [('readonly', False)]})
    location_dest_id = fields.Many2one('stock.location', required=True, string="Destination Location Zone",
                                           default=_default_location_destination, readonly=True, states={'draft': [('readonly', False)]})
    move_lines = fields.One2many('stock.move', 'picking_id', string="Stock Moves", copy=True)
    move_lines_related = fields.One2many(related='move_lines', comodel_name='stock.move', string="Move Lines")
    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, required=True)
    picking_type_code = fields.Selection(related='picking_type_id.code', selection=[('incoming', 'Suppliers'), ('outgoing', 'Customers'), ('internal', 'Internal')])
    picking_type_entire_packs = fields.Boolean(related='picking_type_id.show_entire_packs')
    priority = fields.Selection(compute="get_min_max_date", inverse="_set_priority", store=True, selection=procurement.PROCUREMENT_PRIORITIES, string='Priority', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, select=1, help="Priority for this picking. Setting manually a value here would set it as priority for all the moves", track_visibility='onchange', required=True, default='1')
    min_date = fields.Datetime(compute="get_min_max_date", inverse="_set_min_date", search="_search_min_dates",
                  states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, string='Scheduled Date', select=1, help="Scheduled time for the first part of the shipment to be processed. Setting manually a value here would set it as expected date for all the stock moves.", track_visibility='onchange')
    max_date = fields.Datetime(compute="get_min_max_date", string='Max. Expected Date', select=2, help="Scheduled time for the last part of the shipment to be processed")
    date = fields.Datetime('Creation Date', help="Creation Date, usually the time of the order", select=True, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, track_visibility='onchange', default=fields.Datetime.now())
    date_done = fields.Datetime('Date of Transfer', help="Completion Date of Transfer", readonly=True, copy=False)
    quant_reserved_exist = fields.Boolean(compute="_get_quant_reserved_exist", string='Has quants already reserved', help='Check the existance of quants linked to this picking')
    partner_id = fields.Many2one('res.partner', 'Partner', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    company_id = fields.Many2one('res.company', 'Company', required=True, select=True, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, default=lambda self: self.env['res.company']._company_default_get('stock.picking'))
    pack_operation_ids = fields.One2many('stock.pack.operation', 'picking_id', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, string='Related Packing Operations')
    pack_operation_product_ids = fields.One2many('stock.pack.operation', 'picking_id', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, domain=[('product_id', '!=', False)], string='Non pack')
    pack_operation_pack_ids = fields.One2many('stock.pack.operation', 'picking_id', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, domain=[('product_id', '=', False)], string='Pack')
    pack_operation_exist = fields.Boolean(compute="_get_pack_operation_exist", string='Has Pack Operations', help='Check the existance of pack operation on the picking')
    owner_id = fields.Many2one('res.partner', 'Owner', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, help="Default Owner")
    printed = fields.Boolean(default=False)
    #  Used to search on pickings
    product_id = fields.Many2one(related='move_lines.product_id', comodel_name='product.product', string='Product')
    recompute_pack_op = fields.Boolean('Recompute pack operation?', help='True if reserved quants changed, which mean we might need to recompute the package operations', copy=False, default=False)
    group_id = fields.Many2one(related='move_lines.group_id', comodel_name='procurement.group', string='Procurement Group', readonly=True, store=True)
    launch_pack_operations = fields.Boolean("Launch Pack Operations", copy=False, default=False)

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Reference must be unique per company!'),
    ]

    @api.multi
    def do_print_picking(self):
        '''This function prints the picking list'''
        self.with_context(active_ids=self.ids)
        self.write({'printed': True})
        return self.env["report"].get_action(self.ids, 'stock.report_picking')

    @api.multi
    def launch_packops(self):
        self.write({'launch_pack_operations': True})

    @api.multi
    def action_confirm(self):
        todo = []
        todo_force_assign = []
        for picking in self:
            if not picking.move_lines:
                picking.launch_packops()
            if picking.location_id.usage in ('supplier', 'inventory', 'production'):
                todo_force_assign.append(picking.id)
            for r in picking.move_lines:
                if r.state == 'draft':
                    todo.append(r.id)
        if len(todo):
            self.env['stock.move'].browse(todo).action_confirm()

        if todo_force_assign:
            self.browse(todo_force_assign).force_assign()
        return True

    @api.multi
    def action_assign(self):
        """ Check availability of picking moves.
        This has the effect of changing the state and reserve quants on available moves, and may
        also impact the state of the picking as it is computed based on move's states.
        @return: True
        """
        for pick in self:
            if pick.state == 'draft':
                pick.action_confirm()
            #skip the moves that don't need to be checked
            move_ids = pick.move_lines.filtered(lambda x: x.state not in ('draft', 'cancel', 'done'))
            if not move_ids.ids:
                raise UserError(_('Nothing to check the availability for.'))
            move_ids.action_assign()
        return True

    @api.multi
    def force_assign(self):
        """ Changes state of picking to available if moves are confirmed or waiting.
        @return: True
        """
        for pick in self:
            move_ids = pick.move_lines.filtered(lambda x: x.state in ['confirmed', 'waiting'])
            move_ids.force_assign()
        return True

    @api.multi
    def action_cancel(self):
        for pick in self:
            pick.move_lines.action_cancel()
        return True

    @api.multi
    def action_done(self):
        """Changes picking state to done by processing the Stock Moves of the Picking

        Normally that happens when the button "Done" is pressed on a Picking view.
        @return: True
        """
        for pick in self:
            todo = []
            for move in pick.move_lines:
                if move.state == 'draft':
                    todo.extend(move.action_confirm())
                elif move.state in ('assigned', 'confirmed'):
                    todo.append(move.id)
            if len(todo):
                self.env['stock.move'].browse(todo).action_done()
        return True

    @api.multi
    def unlink(self):
        #on picking deletion, cancel its move then unlink them too
        for pick in self:
            pick.move_lines.action_cancel()
            pick.move_lines.unlink()
        return super(StockPicking, self).unlink()

    @api.model
    def _create_backorder(self, picking, backorder_moves=[]):
        """ Move all non-done lines into a new backorder picking. If the key 'do_only_split' is given in the context, then move all lines not in context.get('split', []) instead of all non-done lines.
        """
        if not backorder_moves:
            backorder_moves = picking.move_lines
        backorder_move_ids = [x.id for x in backorder_moves if x.state not in ('done', 'cancel')]
        if 'do_only_split' in picking.env.context and self.env.context['do_only_split']:
            backorder_move_ids = [x.id for x in backorder_moves if x.id not in self.env.context.get('split', [])]

        if backorder_move_ids:
            backorder = picking.copy({
                'name': '/',
                'move_lines': [],
                'pack_operation_ids': [],
                'backorder_id': picking.id,
            })
            picking.message_post(body=_("Back order <em>%s</em> <b>created</b>.") % (backorder.name))
            self.env["stock.move"].browse(backorder_move_ids).write({'picking_id': backorder.id})

            if not picking.date_done:
                picking.write({'date_done': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)})
            backorder.action_confirm()
            backorder.action_assign()
            return backorder
        return False

    @api.multi
    def recheck_availability(self):
        self.action_assign()
        self.do_prepare_partial()

    @api.model
    def _get_top_level_packages(self, quants_suggested_locations):
        """This method searches for the higher level packages that can be moved as a single operation, given a list of quants
           to move and their suggested destination, and returns the list of matching packages.
        """
        # Try to find as much as possible top-level packages that can be moved
        quant_obj = self.env["stock.quant"]
        top_lvl_packages = set()
        quants_to_compare = quants_suggested_locations.keys()
        for pack in list(set([x.package_id for x in quants_suggested_locations.keys() if x and x.package_id])):
            loop = True
            test_pack = pack
            good_pack = False
            pack_destination = False
            while loop:
                pack_quants = test_pack.get_content().ids
                all_in = True
                for quant in quant_obj.browse(pack_quants):
                    # If the quant is not in the quants to compare and not in the common location
                    if not quant in quants_to_compare:
                        all_in = False
                        break
                    else:
                        #if putaway strat apply, the destination location of each quant may be different (and thus the package should not be taken as a single operation)
                        if not pack_destination:
                            pack_destination = quants_suggested_locations[quant]
                        elif pack_destination != quants_suggested_locations[quant]:
                            all_in = False
                            break
                if all_in:
                    good_pack = test_pack
                    if test_pack.parent_id:
                        test_pack = test_pack.parent_id
                    else:
                        #stop the loop when there's no parent package anymore
                        loop = False
                else:
                    #stop the loop when the package test_pack is not totally reserved for moves of this picking
                    #(some quants may be reserved for other picking or not reserved at all)
                    loop = False
            if good_pack:
                top_lvl_packages.add(good_pack)
        return list(top_lvl_packages)

    @api.model
    def _prepare_pack_ops(self, picking, quants, forced_qties):
        """ returns a list of dict, ready to be used in create() of stock.pack.operation.

        :param picking: browse record (stock.picking)
        :param quants: browse record list (stock.quant). List of quants associated to the picking
        :param forced_qties: dictionary showing for each product (keys) its corresponding quantity (value) that is not covered by the quants associated to the picking
        """
        def _picking_putaway_apply(product):
            location = False
            # Search putaway strategy
            if product_putaway_strats.get(product.id):
                location = product_putaway_strats[product.id]
            else:
                location = self.env['stock.location'].get_putaway_strategy(picking.location_dest_id, product)
                product_putaway_strats[product.id] = location
            return location or picking.location_dest_id.id

        # If we encounter an UoM that is smaller than the default UoM or the one already chosen, use the new one instead.
        product_uom = {}  # Determines UoM used in pack operations
        location_dest_id = None
        location_id = None
        for move in [x for x in picking.move_lines if x.state not in ('done', 'cancel')]:
            if not product_uom.get(move.product_id.id):
                product_uom[move.product_id.id] = move.product_id.uom_id
            if move.product_uom.id != move.product_id.uom_id.id and move.product_uom.factor > product_uom[move.product_id.id].factor:
                product_uom[move.product_id.id] = move.product_uom
            if not move.scrapped:
                if location_dest_id and move.location_dest_id.id != location_dest_id:
                    raise UserError(_('The destination location must be the same for all the moves of the picking.'))
                location_dest_id = move.location_dest_id.id
                if location_id and move.location_id.id != location_id:
                    raise UserError(_('The source location must be the same for all the moves of the picking.'))
                location_id = move.location_id.id

        quant_obj = self.env["stock.quant"]
        vals = []
        qtys_grouped = {}
        lots_grouped = {}
        #for each quant of the picking, find the suggested location
        quants_suggested_locations = {}
        product_putaway_strats = {}
        for quant in quants:
            if quant.qty <= 0:
                continue
            suggested_location_id = _picking_putaway_apply(quant.product_id)
            quants_suggested_locations[quant] = suggested_location_id

        #find the packages we can movei as a whole
        top_lvl_packages = self._get_top_level_packages(quants_suggested_locations)
        # and then create pack operations for the top-level packages found
        for pack in top_lvl_packages:
            pack_quants = quant_obj.browse(pack.get_content().ids)
            vals.append({
                    'picking_id': picking.id,
                    'package_id': pack.id,
                    'product_qty': 1.0,
                    'location_id': pack.location_id.id,
                    'location_dest_id': quants_suggested_locations[pack_quants[0]],
                    'owner_id': pack.owner_id.id,
                })
            #remove the quants inside the package so that they are excluded from the rest of the computation
            for quant in pack_quants:
                del quants_suggested_locations[quant]
        # Go through all remaining reserved quants and group by product, package, owner, source location and dest location
        # Lots will go into pack operation lot object
        for quant, dest_location_id in quants_suggested_locations.items():
            key = (quant.product_id.id, quant.package_id.id, quant.owner_id.id, quant.location_id.id, dest_location_id)
            if qtys_grouped.get(key):
                qtys_grouped[key] += quant.qty
            else:
                qtys_grouped[key] = quant.qty
            if quant.product_id.tracking != 'none' and quant.lot_id:
                lots_grouped.setdefault(key, {}).setdefault(quant.lot_id.id, 0.0)
                lots_grouped[key][quant.lot_id.id] += quant.qty

        # Do the same for the forced quantities (in cases of force_assign or incomming shipment for example)
        for product, qty in forced_qties.items():
            if qty <= 0:
                continue
            suggested_location_id = _picking_putaway_apply(product)
            key = (product.id, False, picking.owner_id.id, picking.location_id.id, suggested_location_id)
            if qtys_grouped.get(key):
                qtys_grouped[key] += qty
            else:
                qtys_grouped[key] = qty

        # Create the necessary operations for the grouped quants and remaining qtys
        prevals = {}
        for key, qty in qtys_grouped.items():
            product = self.env["product.product"].browse(key[0])
            uom_id = product.uom_id.id
            qty_uom = qty
            if product_uom.get(key[0]):
                uom_id = product_uom[key[0]].id
                qty_uom = self.env['product.uom']._compute_qty(product.uom_id.id, qty, uom_id)
            pack_lot_ids = []
            if lots_grouped.get(key):
                for lot in lots_grouped[key].keys():
                    pack_lot_ids += [(0, 0, {'lot_id': lot, 'qty': 0.0, 'qty_todo': lots_grouped[key][lot]})]
            val_dict = {
                'picking_id': picking.id,
                'product_qty': qty_uom,
                'product_id': key[0],
                'package_id': key[1],
                'owner_id': key[2],
                'location_id': key[3],
                'location_dest_id': key[4],
                'product_uom_id': uom_id,
                'pack_lot_ids': pack_lot_ids,
            }
            if key[0] in prevals:
                prevals[key[0]].append(val_dict)
            else:
                prevals[key[0]] = [val_dict]
        # prevals var holds the operations in order to create them in the same order than the picking stock moves if possible
        processed_products = set()
        for move in [x for x in picking.move_lines if x.state not in ('done', 'cancel')]:
            if move.product_id.id not in processed_products:
                vals += prevals.get(move.product_id.id, [])
                processed_products.add(move.product_id.id)
        return vals

    @api.multi
    def do_prepare_partial(self):
        pack_operation_obj = self.env['stock.pack.operation']

        #get list of existing operations and delete them
        existing_package_ids = pack_operation_obj.search([('picking_id', 'in', self.ids)])
        if existing_package_ids:
            existing_package_ids.unlink()
        for picking in self:
            forced_qties = {}  # Quantity remaining after calculating reserved quants
            picking_quants = []
            #Calculate packages, reserved quants, qtys of this picking's moves
            for move in picking.move_lines:
                if move.state not in ('assigned', 'confirmed', 'waiting'):
                    continue
                move_quants = move.reserved_quant_ids
                picking_quants += move_quants
                forced_qty = (move.state == 'assigned') and move.product_qty - sum([x.qty for x in move_quants]) or 0
                #if we used force_assign() on the move, or if the move is incoming, forced_qty > 0
                if float_compare(forced_qty, 0, precision_rounding=move.product_id.uom_id.rounding) > 0:
                    if forced_qties.get(move.product_id):
                        forced_qties[move.product_id] += forced_qty
                    else:
                        forced_qties[move.product_id] = forced_qty
            for vals in self._prepare_pack_ops(picking, picking_quants, forced_qties):
                vals['fresh_record'] = False
                pack_operation_obj.create(vals)
        #recompute the remaining quantities all at once
        self.do_recompute_remaining_quantities()
        self.write({'recompute_pack_op': False})

    @api.multi
    def do_unreserve(self):
        """
          Will remove all quants for picking in picking_ids
        """
        moves_to_unreserve = []
        pack_line_to_unreserve = []
        for picking in self:
            moves_to_unreserve += [m.id for m in picking.move_lines if m.state not in ('done', 'cancel')]
            pack_line_to_unreserve += [p.id for p in picking.pack_operation_ids]
        if moves_to_unreserve:
            if pack_line_to_unreserve:
                self.env['stock.pack.operation'].browse(pack_line_to_unreserve).unlink()
            self.env['stock.move'].browse(moves_to_unreserve).do_unreserve()

    @api.model
    def recompute_remaining_qty(self, picking, done_qtys=False):
        def _create_link_for_index(operation_id, index, product_id, qty_to_assign, quant_id=False):
            move_dict = prod2move_ids[product_id][index]
            qty_on_link = min(move_dict['remaining_qty'], qty_to_assign)
            self.env['stock.move.operation.link'].create({'move_id': move_dict['move'].id, 'operation_id': operation_id, 'qty': qty_on_link, 'reserved_quant_id': quant_id})
            if move_dict['remaining_qty'] == qty_on_link:
                prod2move_ids[product_id].pop(index)
            else:
                move_dict['remaining_qty'] -= qty_on_link
            return qty_on_link

        def _create_link_for_quant(operation_id, quant, qty):
            """create a link for given operation and reserved move of given quant, for the max quantity possible, and returns this quantity"""
            if not quant.reservation_id:
                return _create_link_for_product(operation_id, quant.product_id.id, qty)
            qty_on_link = 0
            for i in range(0, len(prod2move_ids[quant.product_id.id])):
                if prod2move_ids[quant.product_id.id][i]['move'].id != quant.reservation_id.id:
                    continue
                qty_on_link = _create_link_for_index(operation_id, i, quant.product_id.id, qty, quant_id=quant.id)
                break
            return qty_on_link

        def _create_link_for_product(operation_id, product_id, qty):
            '''method that creates the link between a given operation and move(s) of given product, for the given quantity.
            Returns True if it was possible to create links for the requested quantity (False if there was not enough quantity on stock moves)'''
            qty_to_assign = qty
            product = self.env["product.product"].browse(product_id)
            rounding = product.uom_id.rounding
            qtyassign_cmp = float_compare(qty_to_assign, 0.0, precision_rounding=rounding)
            if prod2move_ids.get(product_id):
                while prod2move_ids[product_id] and qtyassign_cmp > 0:
                    qty_on_link = _create_link_for_index(operation_id, 0, product_id, qty_to_assign, quant_id=False)
                    qty_to_assign -= qty_on_link
                    qtyassign_cmp = float_compare(qty_to_assign, 0.0, precision_rounding=rounding)
            return qtyassign_cmp == 0

        uom_obj = self.env['product.uom']
        quants_in_package_done = set()
        prod2move_ids = {}
        still_to_do = []
        #make a dictionary giving for each product, the moves and related quantity that can be used in operation links
        for move in picking.move_lines.filtered(lambda x: x.state not in ('done', 'cancel')):
            if not prod2move_ids.get(move.product_id.id):
                prod2move_ids[move.product_id.id] = [{'move': move, 'remaining_qty': move.product_qty}]
            else:
                prod2move_ids[move.product_id.id].append({'move': move, 'remaining_qty': move.product_qty})

        need_rereserve = False
        #sort the operations in order to give higher priority to those with a package, then a serial number
        operations = picking.pack_operation_ids
        operations = sorted(operations, key=lambda x: ((x.package_id and not x.product_id) and -4 or 0) + (x.package_id and -2 or 0) + (x.pack_lot_ids and -1 or 0))
        #delete existing operations to start again from scratch
        links = self.env['stock.move.operation.link'].search([('operation_id', 'in', [x.id for x in operations])])
        if links:
            links.unlink()
        #1) first, try to create links when quants can be identified without any doubt
        for ops in operations:
            lot_qty = {}
            for packlot in ops.pack_lot_ids:
                lot_qty[packlot.lot_id.id] = uom_obj._compute_qty(ops.product_uom_id.id, packlot.qty, ops.product_id.uom_id.id)
            #for each operation, create the links with the stock move by seeking on the matching reserved quants,
            #and deffer the operation if there is some ambiguity on the move to select
            if ops.package_id and not ops.product_id and (not done_qtys or ops.qty_done):
                #entire package
                for quant in self.env['stock.quant'].browse(ops.package_id.get_content().ids):
                    remaining_qty_on_quant = quant.qty
                    if quant.reservation_id:
                        #avoid quants being counted twice
                        quants_in_package_done.add(quant.id)
                        qty_on_link = _create_link_for_quant(ops.id, quant, quant.qty)
                        remaining_qty_on_quant -= qty_on_link
                    if remaining_qty_on_quant:
                        still_to_do.append((ops, quant.product_id.id, remaining_qty_on_quant))
                        need_rereserve = True
            elif ops.product_id:
                #Check moves with same product
                product_qty = ops.qty_done if done_qtys else ops.product_qty
                qty_to_assign = uom_obj._compute_qty_obj(ops.product_uom_id, product_qty, ops.product_id.uom_id)
                for move_dict in prod2move_ids.get(ops.product_id.id, []):
                    move = move_dict['move']
                    for quant in move.reserved_quant_ids:
                        if not qty_to_assign > 0:
                            break
                        if quant.id in quants_in_package_done:
                            continue

                        #check if the quant is matching the operation details
                        if ops.package_id:
                            flag = quant.package_id and bool(self.env['stock.quant.package'].search([('id', 'child_of', [ops.package_id.id])])) or False
                        else:
                            flag = not quant.package_id.id
                        flag = flag and (ops.owner_id.id == quant.owner_id.id)
                        if flag:
                            if not lot_qty:
                                max_qty_on_link = min(quant.qty, qty_to_assign)
                                qty_on_link = _create_link_for_quant(ops.id, quant, max_qty_on_link)
                                qty_to_assign -= qty_on_link
                            else:
                                if lot_qty.get(quant.lot_id.id):  # if there is still some qty left
                                    max_qty_on_link = min(quant.qty, qty_to_assign, lot_qty[quant.lot_id.id])
                                    qty_on_link = _create_link_for_quant(ops.id, quant, max_qty_on_link)
                                    qty_to_assign -= qty_on_link
                                    lot_qty[quant.lot_id.id] -= qty_on_link

                qty_assign_cmp = float_compare(qty_to_assign, 0, precision_rounding=ops.product_id.uom_id.rounding)
                if qty_assign_cmp > 0:
                    #qty reserved is less than qty put in operations. We need to create a link but it's deferred after we processed
                    #all the quants (because they leave no choice on their related move and needs to be processed with higher priority)
                    still_to_do += [(ops, ops.product_id.id, qty_to_assign)]
                    need_rereserve = True

        #2) then, process the remaining part
        all_op_processed = True
        for ops, product_id, remaining_qty in still_to_do:
            all_op_processed = _create_link_for_product(ops.id, product_id, remaining_qty) and all_op_processed
        return (need_rereserve, all_op_processed)

    @api.model
    def picking_recompute_remaining_quantities(self, picking, done_qtys=False):
        need_rereserve = False
        all_op_processed = True
        if picking.pack_operation_ids:
            need_rereserve, all_op_processed = self.recompute_remaining_qty(picking, done_qtys=done_qtys)
        return need_rereserve, all_op_processed

    @api.multi
    def do_recompute_remaining_quantities(self, done_qtys=False):
        for picking in self:
            if picking.pack_operation_ids:
                self.recompute_remaining_qty(picking, done_qtys=done_qtys)

    @api.model
    def _prepare_values_extra_move(self, op, product, remaining_qty):
        """
        Creates an extra move when there is no corresponding original move to be copied
        """
        uom_id = product.uom_id.id
        qty = remaining_qty
        if op.product_id and op.product_uom_id and op.product_uom_id.id != product.uom_id.id:
            if op.product_uom_id.factor > product.uom_id.factor:  # If the pack operation's is a smaller unit
                uom_id = op.product_uom_id.id
                #HALF-UP rounding as only rounding errors will be because of propagation of error from default UoM
                qty = self.env["product.uom"]._compute_qty_obj(product.uom_id, remaining_qty, op.product_uom_id, rounding_method='HALF-UP')
        picking = op.picking_id
        ref = product.default_code
        name = '[' + ref + ']' + ' ' + product.name if ref else product.name
        res = {
            'picking_id': picking.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'product_id': product.id,
            'product_uom': uom_id,
            'product_uom_qty': qty,
            'name': _('Extra Move: ') + name,
            'state': 'draft',
            'restrict_partner_id': op.owner_id,
            'group_id': picking.group_id.id,
            }
        return res

    @api.model
    def _create_extra_moves(self, picking):
        '''This function creates move lines on a picking, at the time of do_transfer, based on
        unexpected product transfers (or exceeding quantities) found in the pack operations.
        '''
        moves = []
        StockMove = self.env['stock.move']
        for op in picking.pack_operation_ids:
            for product_id, remaining_qty in self.env['stock.pack.operation']._get_remaining_prod_quantities(op).items():
                if float_compare(remaining_qty, 0, precision_rounding=product_id.uom_id.rounding) > 0:
                    vals = self._prepare_values_extra_move(op, product_id, remaining_qty)
                    moves.append(StockMove.create(vals).id)
        if moves:
            StockMove.browse(moves).action_confirm()
        return moves

    @api.multi
    def rereserve_pick(self):
        """
        This can be used to provide a button that rereserves taking into account the existing pack operations
        """
        for pick in self:
            self.rereserve_quants(pick, move_ids=pick.move_lines.ids)

    @api.model
    def rereserve_quants(self, picking, move_ids=[]):
        """ Unreserve quants then try to reassign quants."""
        stock_move_obj = self.env['stock.move']
        if not move_ids:
            picking.do_unreserve()
            picking.action_assign()
        else:
            move = stock_move_obj.browse(move_ids)
            move.do_unreserve()
            move.action_assign(no_prepare=True)

    @api.multi
    def do_new_transfer(self):
        for pick in self:
            to_delete = []
            if not pick.move_lines and not pick.pack_operation_ids:
                raise UserError(_('Please create some Initial Demand or Mark as Todo and create some Operations. '))
            # In draft or with no pack operations edited yet, ask if we can just do everything
            if pick.state == 'draft' or all([x.qty_done == 0.0 for x in pick.pack_operation_ids]):
                # If no lots when needed, raise error
                picking_type = pick.picking_type_id
                if (picking_type.use_create_lots or picking_type.use_existing_lots):
                    for pack in pick.pack_operation_ids:
                        if pack.product_id and pack.product_id.tracking != 'none':
                            raise UserError(_('Some products require lots, so you need to specify those first!'))
                view = self.env.ref('stock.view_immediate_transfer').id
                wiz_id = self.env['stock.immediate.transfer'].create({'pick_id': pick.id})
                return {
                     'name': _('Immediate Transfer?'),
                     'type': 'ir.actions.act_window',
                     'view_type': 'form',
                     'view_mode': 'form',
                     'res_model': 'stock.immediate.transfer',
                     'views': [(view, 'form')],
                     'view_id': view,
                     'target': 'new',
                     'res_id': wiz_id,
                     'context': self.env.context,
                 }

            # Check backorder should check for other barcodes
            if self.check_backorder(pick):
                view = self.env.ref('stock.view_backorder_confirmation').id
                wiz_id = self.env['stock.backorder.confirmation'].create({'pick_id': pick.id})
                return {
                         'name': _('Create Backorder?'),
                         'type': 'ir.actions.act_window',
                         'view_type': 'form',
                         'view_mode': 'form',
                         'res_model': 'stock.backorder.confirmation',
                         'views': [(view, 'form')],
                         'view_id': view,
                         'target': 'new',
                         'res_id': wiz_id.id,
                         'context': self.env.context,
                     }
            for operation in pick.pack_operation_ids:
                if operation.qty_done < 0:
                    raise UserError(_('No negative quantities allowed'))
                if operation.qty_done > 0:
                    operation.write({'product_qty': operation.qty_done})
                else:
                    to_delete.append(operation.id)
            if to_delete:
                self.env['stock.pack.operation'].browse(to_delete).unlink()
        self.do_transfer()
        return

    @api.model
    def check_backorder(self, picking):
        need_rereserve, all_op_processed = self.picking_recompute_remaining_quantities(picking, done_qtys=True)
        for move in picking.move_lines:
            if float_compare(move.remaining_qty, 0, precision_rounding=move.product_id.uom_id.rounding) != 0:
                return True
        return False

    @api.multi
    def create_lots_for_picking(self):
        to_unlink = []
        for picking in self:
            for ops in picking.pack_operation_ids:
                for opslot in ops.pack_lot_ids:
                    if not opslot.lot_id:
                        lot_id = self.env['stock.production.lot'].create({'name': opslot.lot_name, 'product_id': ops.product_id.id})
                        opslot.write({'lot_id': lot_id.id})
                #Unlink pack operations where qty = 0
                to_unlink += [x.id for x in ops.pack_lot_ids if x.qty == 0.0]
        self.env['stock.pack.operation.lot'].browse(to_unlink).unlink()

    @api.multi
    def do_transfer(self):
        """
            If no pack operation, we do simple action_done of the picking
            Otherwise, do the pack operations
        """
        stock_move_obj = self.env['stock.move']
        self.create_lots_for_picking()
        for picking in self:
            if not picking.pack_operation_ids:
                picking.action_done()
                continue
            else:
                need_rereserve, all_op_processed = self.picking_recompute_remaining_quantities(picking)
                #create extra moves in the picking (unexpected product moves coming from pack operations)
                todo_move_ids = []
                if not all_op_processed:
                    todo_move_ids += self._create_extra_moves(picking)

                #split move lines if needed
                toassign_move_ids = []
                for move in picking.move_lines:
                    remaining_qty = move.remaining_qty
                    if move.state in ('done', 'cancel'):
                        #ignore stock moves cancelled or already done
                        continue
                    elif move.state == 'draft':
                        toassign_move_ids.append(move.id)
                    if float_compare(remaining_qty, 0, precision_rounding=move.product_id.uom_id.rounding) == 0:
                        if move.state in ('draft', 'assigned', 'confirmed'):
                            todo_move_ids.append(move.id)
                    elif float_compare(remaining_qty, 0, precision_rounding=move.product_id.uom_id.rounding) > 0 and \
                                float_compare(remaining_qty, move.product_qty, precision_rounding=move.product_id.uom_id.rounding) < 0:
                        new_move = stock_move_obj.split(move, remaining_qty)
                        todo_move_ids.append(move.id)
                        #Assign move as it was assigned before
                        toassign_move_ids.append(new_move)
                todo_move_ids = list(set(todo_move_ids))
                if not all_op_processed or need_rereserve:
                    if not picking.location_id.usage in ("supplier", "production", "inventory"):
                        self.rereserve_quants(picking, move_ids=todo_move_ids)
                    picking.do_recompute_remaining_quantities()
                if todo_move_ids and not self.env.context.get('do_only_split'):
                    stock_move_obj.browse(todo_move_ids).action_done()
                elif self.env.context.get('do_only_split'):
                    self.with_context(split=todo_move_ids)
            self._create_backorder(picking)
        return True

    @api.model
    def do_split(self, picking_ids):
        """ just split the picking (create a backorder) without making it 'done' """
        return picking_ids.with_context(do_only_split=True).do_transfer()

    @api.multi
    def put_in_pack(self):
        stock_operation_obj = self.env["stock.pack.operation"]
        package_obj = self.env["stock.quant.package"]
        package_id = False
        for pick in self:
            operations = [x for x in pick.pack_operation_ids if x.qty_done > 0 and (not x.result_package_id)]
            pack_operation_ids = []
            for operation in operations:
                #If we haven't done all qty in operation, we have to split into 2 operation
                op = operation
                if operation.qty_done < operation.product_qty:
                    new_operation = operation.copy({'product_qty': operation.qty_done, 'qty_done': operation.qty_done})

                    operation.write({'product_qty': operation.product_qty - operation.qty_done, 'qty_done': 0})
                    if operation.pack_lot_ids:
                        packlots_transfer = [(4, x.id) for x in operation.pack_lot_ids]
                        new_operation.write({'pack_lot_ids': packlots_transfer})

                    op = new_operation
                pack_operation_ids.append(op.id)
            if operations:
                pack_operation = stock_operation_obj.browse(pack_operation_ids)
                pack_operation.check_tracking()
                package_id = package_obj.create({})
                pack_operation.write({'result_package_id': package_id})
            else:
                raise UserError(_('Please process some quantities to put in the pack first!'))
        return package_id.id
