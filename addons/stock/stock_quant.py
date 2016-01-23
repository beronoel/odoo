# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from openerp.tools.float_utils import float_compare, float_round
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from odoo import models, fields, api, _


#----------------------------------------------------------
# Quants
#----------------------------------------------------------
class StockQuant(models.Model):
    """
    Quants are the smallest unit of stock physical instances
    """
    _name = "stock.quant"
    _description = "Quants"

    @api.multi
    def _get_quant_name(self):
        """ Forms complete name of location from parent location to child location.
        @return: Dictionary of values
        """
        for q in self:
            q.name = q.product_id.code or ''
            if q.lot_id:
                q.name = q.lot_id.name
            q.name += ': ' + str(q.qty) + q.product_id.uom_id.name

    @api.multi
    def _calc_inventory_value(self):
        uid_company_id = self.env.user.company_id.id
        for quant in self:
            # self._context.pop('force_company')
            if quant.company_id.id != uid_company_id:
                #if the company of the quant is different than the current user company, force the company in the context
                #then re-do a browse to read the property fields for the good company.
                quant.with_context(force_company=quant.company_id.id)
            quant.inventory_value = quant._get_inventory_value()

    @api.multi
    def _get_inventory_value(self):
        return self.product_id.standard_price * self.qty

    name = fields.Char(compute="_get_quant_name", string='Identifier')
    product_id = fields.Many2one('product.product', 'Product', required=True, ondelete="restrict", readonly=True, select=True)
    location_id = fields.Many2one('stock.location', 'Location', required=True, ondelete="restrict", readonly=True, select=True, auto_join=True)
    qty = fields.Float('Quantity', required=True, help="Quantity of products in this quant, in the default unit of measure of the product", readonly=True, select=True)
    product_uom_id = fields.Many2one(related='product_id.uom_id', relation="product.uom", string='Unit of Measure', readonly=True)
    package_id = fields.Many2one('stock.quant.package', string='Package', help="The package containing this quant", readonly=True, select=True)
    packaging_type_id = fields.Many2one(related='package_id.packaging_id', relation='product.packaging', string='Type of packaging', readonly=True, store=True)
    reservation_id = fields.Many2one('stock.move', 'Reserved for Move', help="The move the quant is reserved for", readonly=True, select=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot', readonly=True, select=True, ondelete="restrict")
    cost = fields.Float('Unit Cost')
    owner_id = fields.Many2one('res.partner', 'Owner', help="This is the owner of the quant", readonly=True, select=True)
    create_date = fields.Datetime('Creation Date', readonly=True)
    in_date = fields.Datetime('Incoming Date', readonly=True, select=True)
    history_ids = fields.Many2many('stock.move', 'stock_quant_move_rel', 'quant_id', 'move_id', 'Moves', help='Moves that operate(d) on this quant', copy=False)
    company_id = fields.Many2one('res.company', 'Company', help="The company to which the quants belong", required=True, readonly=True, select=True, default=lambda self: self.env.user.company_id)
    inventory_value = fields.Float(compute="_calc_inventory_value", string="Inventory Value", readonly=True)
    # Used for negative quants to reconcile after compensated by a new positive one
    propagated_from_id = fields.Many2one('stock.quant', 'Linked Quant', help='The negative quant this is coming from', readonly=True, select=True)
    negative_move_id = fields.Many2one('stock.move', 'Move Negative Quant', help='If this is a negative quant, this will be the move that caused this negative quant.', readonly=True)
    negative_dest_location_id = fields.Many2one(related='negative_move_id.location_dest_id', relation='stock.location', string="Negative Destination Location", readonly=True, help="Technical field used to record the destination location of a move that created a negative quant")

    @api.v8
    def init(self):
        self.env.cr.execute('SELECT indexname FROM pg_indexes WHERE indexname = %s', ('stock_quant_product_location_index',))
        if not self.env.cr.fetchone():
            self.env.cr.execute('CREATE INDEX stock_quant_product_location_index ON stock_quant (product_id, location_id, company_id, qty, in_date, reservation_id)')

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        ''' Overwrite the read_group in order to sum the function field 'inventory_value' in group by'''
        res = super(StockQuant, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        if 'inventory_value' in fields:
            for line in res:
                if '__domain' in line:
                    lines = self.search(line['__domain'])
                    inv_value = 0.0
                    for line2 in lines:
                        inv_value += line2.inventory_value
                    line['inventory_value'] = inv_value
        return res

    @api.multi
    def action_view_quant_history(self):
        '''
        This function returns an action that display the history of the quant, which
        mean all the stock moves that lead to this quant creation with this quant quantity.
        '''
        result = self.env.ref('stock.action_move_form2').read()[0]

        move_ids = []
        for quant in self:
            move_ids += [move.id for move in quant.history_ids]

        result['domain'] = "[('id','in',[" + ','.join(map(str, move_ids)) + "])]"
        return result

    # TO DO: fix after all model
    @api.model
    def quants_reserve(self, quants, move, link=False):
        '''This function reserves quants for the given move (and optionally given link). If the total of quantity reserved is enough, the move's state
        is also set to 'assigned'
        '''
        toreserve = []
        reserved_availability = move.reserved_availability
        #split quants if needed
        for quant, qty in quants:
            if qty <= 0.0 or (quant and quant.qty <= 0.0):
                raise UserError(_('You can not reserve a negative quantity or a negative quant.'))
            if not quant:
                continue
            self._quant_split(quant, qty)
            toreserve.append(quant.id)
            reserved_availability += quant.qty
        #reserve quants
        if toreserve:
            self.browse(toreserve).sudo().write({'reservation_id': move.id})
        #check if move'state needs to be set as 'assigned'
        rounding = move.product_id.uom_id.rounding
        if float_compare(reserved_availability, move.product_qty, precision_rounding=rounding) == 0 and move.state in ('confirmed', 'waiting'):
            move.write({'state': 'assigned'})
        elif float_compare(reserved_availability, 0, precision_rounding=rounding) > 0 and not move.partially_available:
            move.write({'partially_available': True})

    @api.model
    def quants_move(self, quants, move, location_to, location_from=False, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False, entire_pack=False):
        """Moves all given stock.quant in the given destination location.  Unreserve from current move.
        :param quants: list of tuple(browse record(stock.quant) or None, quantity to move)
        :param move: browse record (stock.move)
        :param location_to: browse record (stock.location) depicting where the quants have to be moved
        :param location_from: optional browse record (stock.location) explaining where the quant has to be taken (may differ from the move source location in case a removal strategy applied). This parameter is only used to pass to _quant_create if a negative quant must be created
        :param lot_id: ID of the lot that must be set on the quants to move
        :param owner_id: ID of the partner that must own the quants to move
        :param src_package_id: ID of the package that contains the quants to move
        :param dest_package_id: ID of the package that must be set on the moved quant
        """
        quants_reconcile = []
        to_move_quants = []
        self._check_location(location_to)
        for quant, qty in quants:
            if not quant:
                #If quant is None, we will create a quant to move (and potentially a negative counterpart too)
                quant = self._quant_create(qty, move, lot_id=lot_id, owner_id=owner_id, src_package_id=src_package_id, dest_package_id=dest_package_id, force_location_from=location_from, force_location_to=location_to)
            else:
                self._quant_split(quant, qty)
                to_move_quants.append(quant)
            quants_reconcile.append(quant)
        if to_move_quants:
            to_recompute_move_ids = [x.reservation_id.id for x in to_move_quants if x.reservation_id and x.reservation_id.id != move.id]
            self.move_quants_write(to_move_quants, move, location_to, dest_package_id, lot_id=lot_id, entire_pack=entire_pack)
            self.pool['stock.move'].recalculate_move_state(self.env.cr, self.env.uid, to_recompute_move_ids, context=self.env.context)
            # self.env['stock.move'].recalculate_move_state(to_recompute_move_ids)
        if location_to.usage == 'internal':
            # Do manual search for quant to avoid full table scan (order by id)
            self.env.cr.execute("""
                SELECT 0 FROM stock_quant, stock_location WHERE product_id = %s AND stock_location.id = stock_quant.location_id AND
                ((stock_location.parent_left >= %s AND stock_location.parent_left < %s) OR stock_location.id = %s) AND qty < 0.0 LIMIT 1
            """, (move.product_id.id, location_to.parent_left, location_to.parent_right, location_to.id))
            if self.env.cr.fetchone():
                for quant in quants_reconcile:
                    self._quant_reconcile_negative(quant, move)

    @api.model
    def move_quants_write(self, quants, move, location_dest_id, dest_package_id, lot_id=False, entire_pack=False):
        vals = {'location_id': location_dest_id.id,
                'history_ids': [(4, move.id)],
                'reservation_id': False}
        if lot_id and any(x.id for x in quants if not x.lot_id.id):
            vals['lot_id'] = lot_id
        if not entire_pack:
            vals.update({'package_id': dest_package_id})
        self.browse([q.id for q in quants]).sudo().write(vals)

    @api.model
    def quants_get_preferred_domain(self, qty, move, ops=False, lot_id=False, domain=None, preferred_domain_list=[]):
        ''' This function tries to find quants for the given domain and move/ops, by trying to first limit
            the choice on the quants that match the first item of preferred_domain_list as well. But if the qty requested is not reached
            it tries to find the remaining quantity by looping on the preferred_domain_list (tries with the second item and so on).
            Make sure the quants aren't found twice => all the domains of preferred_domain_list should be orthogonal
        '''
        domain = domain or [('qty', '>', 0.0)]
        domain = list(domain)
        quants = [(None, qty)]
        if ops:
            restrict_lot_id = lot_id
            location = ops.location_id
            domain += [('owner_id', '=', ops.owner_id.id)]
            if ops.package_id and not ops.product_id:
                domain += [('package_id', 'child_of', ops.package_id.id)]
            elif ops.package_id and ops.product_id:
                domain += [('package_id', '=', ops.package_id.id)]
            else:
                domain += [('package_id', '=', False)]
            domain += [('location_id', '=', ops.location_id.id)]
        else:
            restrict_lot_id = move.restrict_lot_id.id
            location = move.location_id
            domain += [('owner_id', '=', move.restrict_partner_id.id)]
            domain += [('location_id', 'child_of', move.location_id.id)]
        if self.env.context.get('force_company'):
            domain += [('company_id', '=', self.env.context['force_company'])]
        else:
            domain += [('company_id', '=', move.company_id.id)]
        removal_strategy = self.env['stock.location'].get_removal_strategy(qty, move, ops=ops)
        product = move.product_id
        domain += [('product_id', '=', move.product_id.id)]

        #don't look for quants in location that are of type production, supplier or inventory.
        if location.usage in ['inventory', 'production', 'supplier']:
            return quants
        res_qty = qty
        if restrict_lot_id:
            if not preferred_domain_list:
                preferred_domain_list = [[('lot_id', '=', restrict_lot_id)], [('lot_id', '=', False)]]
            else:
                lot_list = []
                no_lot_list = []
                for pref_domain in preferred_domain_list:
                    pref_lot_domain = pref_domain + [('lot_id', '=', restrict_lot_id)]
                    pref_no_lot_domain = pref_domain + [('lot_id', '=', False)]
                    lot_list.append(pref_lot_domain)
                    no_lot_list.append(pref_no_lot_domain)
                preferred_domain_list = lot_list + no_lot_list

        if not preferred_domain_list:
            return self.quants_get(qty, move, ops=ops, domain=domain, removal_strategy=removal_strategy)
        for preferred_domain in preferred_domain_list:
            res_qty_cmp = float_compare(res_qty, 0, precision_rounding=product.uom_id.rounding)
            if res_qty_cmp > 0:
                #try to replace the last tuple (None, res_qty) with something that wasn't chosen at first because of the preferred order
                quants.pop()
                tmp_quants = self.quants_get(res_qty, move, ops=ops, domain=domain + preferred_domain,
                                             removal_strategy=removal_strategy)
                for quant in tmp_quants:
                    if quant[0]:
                        res_qty -= quant[1]
                quants += tmp_quants
        return quants

    @api.model
    def quants_get(self, qty, move, ops=False, domain=None, removal_strategy='fifo'):
        """
        Use the removal strategies of product to search for the correct quants
        If you inherit, put the super at the end of your method.

        :location: browse record of the parent location where the quants have to be found
        :product: browse record of the product to find
        :qty in UoM of product
        """
        domain = domain or [('qty', '>', 0.0)]
        return self.apply_removal_strategy(qty, move, ops=ops, domain=domain, removal_strategy=removal_strategy)

    @api.model
    def apply_removal_strategy(self, quantity, move, ops=False, domain=None, removal_strategy='fifo'):
        if removal_strategy == 'fifo':
            order = 'in_date, id'
            return self._quants_get_order(quantity, move, ops=ops, domain=domain, orderby=order)
        elif removal_strategy == 'lifo':
            order = 'in_date desc, id desc'
            return self._quants_get_order(quantity, move, ops=ops, domain=domain, orderby=order)
        raise UserError(_('Removal strategy %s not implemented.' % (removal_strategy,)))

    @api.model
    def _quant_create(self, qty, move, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False,
                      force_location_from=False, force_location_to=False):
        '''Create a quant in the destination location and create a negative quant in the source location if it's an internal location.
        '''
        price_unit = self.env['stock.move'].get_price_unit(move)
        location = force_location_to or move.location_dest_id
        rounding = move.product_id.uom_id.rounding
        vals = {
            'product_id': move.product_id.id,
            'location_id': location.id,
            'qty': float_round(qty, precision_rounding=rounding),
            'cost': price_unit,
            'history_ids': [(4, move.id)],
            'in_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'company_id': move.company_id.id,
            'lot_id': lot_id,
            'owner_id': owner_id,
            'package_id': dest_package_id,
        }
        if move.location_id.usage == 'internal':
            #if we were trying to move something from an internal location and reach here (quant creation),
            #it means that a negative quant has to be created as well.
            negative_vals = vals.copy()
            negative_vals['location_id'] = force_location_from and force_location_from.id or move.location_id.id
            negative_vals['qty'] = float_round(-qty, precision_rounding=rounding)
            negative_vals['cost'] = price_unit
            negative_vals['negative_move_id'] = move.id
            negative_vals['package_id'] = src_package_id
            negative_quant_id = self.sudo().create(negative_vals)
            vals.update({'propagated_from_id': negative_quant_id.id})

        # In case of serial tracking, check if the product does not exist somewhere internally already
        picking_type = move.picking_id and move.picking_id.picking_type_id or False
        if lot_id and move.product_id.tracking == 'serial' and (not picking_type or (picking_type.use_create_lots or picking_type.use_existing_lots)):
            if qty != 1.0:
                raise UserError(_('You should only receive by the piece with the same serial number'))
            other_quants = self.search([('product_id', '=', move.product_id.id), ('lot_id', '=', lot_id),
                                                 ('qty', '>', 0.0), ('location_id.usage', '=', 'internal')])
            if other_quants:
                lot_name = self.env['stock.production.lot'].browse(lot_id).name
                raise UserError(_('The serial number %s is already in stock') % lot_name)

        #create the quant as superuser, because we want to restrict the creation of quant manually: we should always use this method to create quants
        quant_id = self.sudo().create(vals)
        return quant_id

    @api.model
    def _quant_split(self, quant, qty):
        rounding = quant.product_id.uom_id.rounding
        if float_compare(abs(quant.qty), abs(qty), precision_rounding=rounding) <= 0:  # if quant <= qty in abs, take it entirely
            return False
        qty_round = float_round(qty, precision_rounding=rounding)
        new_qty_round = float_round(quant.qty - qty, precision_rounding=rounding)
        # Fetch the history_ids manually as it will not do a join with the stock moves then (=> a lot faster)
        self.env.cr.execute("""SELECT move_id FROM stock_quant_move_rel WHERE quant_id = %s""", (quant.id,))
        res = self.env.cr.fetchall()
        new_quant = quant.sudo().copy(default={'qty': new_qty_round, 'history_ids': [(4, x[0]) for x in res]})
        quant.sudo().write({'qty': qty_round})
        return new_quant

    # To DO: stock_account call
    @api.model
    def _get_latest_move(self, quant):
        move = False
        for m in quant.history_ids:
            if not move or m.date > move.date:
                move = m
        return move

    @api.multi
    def _quants_merge(self, solving_quant):
        path = []
        for move in solving_quant.history_ids:
            path.append((4, move.id))
        self.sudo().write({'history_ids': path})

    @api.model
    def _search_quants_to_reconcile(self, quant):
        """
            Searches negative quants to reconcile for where the quant to reconcile is put
        """
        dom = [('qty', '<', 0)]
        order = 'in_date'
        dom += [('location_id', 'child_of', quant.location_id.id), ('product_id', '=', quant.product_id.id),
                ('owner_id', '=', quant.owner_id.id)]
        if quant.package_id.id:
            dom += [('package_id', '=', quant.package_id.id)]
        if quant.lot_id:
            dom += ['|', ('lot_id', '=', False), ('lot_id', '=', quant.lot_id.id)]
            order = 'lot_id, in_date'
        # Do not let the quant eat itself, or it will kill its history (e.g. returns / Stock -> Stock)
        dom += [('id', '!=', quant.propagated_from_id.id)]
        quants_search = self.search(dom, order=order)
        product = quant.product_id
        quants = []
        quantity = quant.qty
        for quant in quants_search:
            rounding = product.uom_id.rounding
            if float_compare(quantity, abs(quant.qty), precision_rounding=rounding) >= 0:
                quants += [(quant, abs(quant.qty))]
                quantity -= abs(quant.qty)
            elif float_compare(quantity, 0.0, precision_rounding=rounding) != 0:
                quants += [(quant, quantity)]
                quantity = 0
                break
        return quants

    @api.model
    def _quant_reconcile_negative(self, quant, move):
        """
            When new quant arrive in a location, try to reconcile it with
            negative quants. If it's possible, apply the cost of the new
            quant to the counterpart of the negative quant.
        """
        solving_quant = quant
        quants = self._search_quants_to_reconcile(quant)
        product_uom_rounding = quant.product_id.uom_id.rounding
        for quant_neg, qty in quants:
            if not quant_neg or not solving_quant:
                continue
            to_solve_quant_ids = self.search([('propagated_from_id', '=', quant_neg.id)])
            if not to_solve_quant_ids:
                continue
            solving_qty = qty
            solved_quant_ids = []
            for to_solve_quant in to_solve_quant_ids:
                if float_compare(solving_qty, 0, precision_rounding=product_uom_rounding) <= 0:
                    continue
                solved_quant_ids.append(to_solve_quant.id)
                self._quant_split(to_solve_quant, min(solving_qty, to_solve_quant.qty))
                solving_qty -= min(solving_qty, to_solve_quant.qty)
            remaining_solving_quant = self._quant_split(solving_quant, qty)
            remaining_neg_quant = self._quant_split(quant_neg, -qty)
            #if the reconciliation was not complete, we need to link together the remaining parts
            if remaining_neg_quant:
                remaining_to_solve_quant_ids = self.search([('propagated_from_id', '=', quant_neg.id), ('id', 'not in', solved_quant_ids)])
                if remaining_to_solve_quant_ids:
                    remaining_to_solve_quant_ids.sudo().write({'propagated_from_id': remaining_neg_quant.id})
            if solving_quant.propagated_from_id and solved_quant_ids:
                self.browse(solved_quant_ids).sudo().write({'propagated_from_id': solving_quant.propagated_from_id.id})
            #delete the reconciled quants, as it is replaced by the solved quants
            quant_neg.sudo().unlink()
            if solved_quant_ids:
                #price update + accounting entries adjustments
                self.browse(solved_quant_ids)._price_update(solving_quant.cost)
                #merge history (and cost?)
                self.browse(solved_quant_ids)._quants_merge(solving_quant)
            solving_quant.sudo().unlink()
            solving_quant = remaining_solving_quant

    @api.multi
    def _price_update(self, newprice):
        self.sudo().write({'cost': newprice})

    # To Do all MIG stock model
    @api.model
    def quants_unreserve(self, move):
        related_quants = move.reserved_quant_ids
        if related_quants:
            #if move has a picking_id, write on that picking that pack_operation might have changed and need to be recomputed
            if move.partially_available:
                move.write({'partially_available': False})
            related_quants.sudo().write({'reservation_id': False})

    @api.model
    def _quants_get_order(self, quantity, move, ops=False, domain=[], orderby='in_date'):
        ''' Implementation of removal strategies
            If it can not reserve, it will return a tuple (None, qty)
        '''
        res = []
        offset = 0
        while float_compare(quantity, 0, precision_rounding=move.product_id.uom_id.rounding) > 0:
            quants = self.search(domain, order=orderby, limit=10, offset=offset)
            if not quants:
                res.append((None, quantity))
                break
            for quant in quants:
                rounding = move.product_id.uom_id.rounding
                if float_compare(quantity, abs(quant.qty), precision_rounding=rounding) >= 0:
                    res += [(quant, abs(quant.qty))]
                    quantity -= abs(quant.qty)
                elif float_compare(quantity, 0.0, precision_rounding=rounding) != 0:
                    res += [(quant, quantity)]
                    quantity = 0
                    break
            offset += 10
        return res

    @api.model
    def _check_location(self, location_to):
        if location_to.usage == 'view':
            raise UserError(_('You cannot move to a location of type view %s.') % (location_to.name))
        return True
