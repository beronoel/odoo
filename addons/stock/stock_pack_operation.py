# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import openerp.addons.decimal_precision as dp
from openerp.tools.float_utils import float_round
from openerp.exceptions import UserError
from odoo import models, fields, api, _


class StockPackOperation(models.Model):
    _name = "stock.pack.operation"
    _description = "Packing Operation"

    _order = "result_package_id desc, id"

    @api.model
    def _get_remaining_prod_quantities(self, operation):
        '''Get the remaining quantities per product on an operation with a package. This function returns a dictionary'''
        #if the operation doesn't concern a package, it's not relevant to call this function
        if not operation.package_id or operation.product_id:
            return {operation.product_id: operation.remaining_qty}
        #get the total of products the package contains
        # res = self.package_id._get_all_products_quantities()
        res = self.env['stock.quant.package']._get_all_products_quantities(self.package_id)
        #reduce by the quantities linked to a move
        for record in operation.linked_move_operation_ids:
            if record.move_id.product_id.id not in res:
                res[record.move_id.product_id] = 0
            res[record.move_id.product_id] -= record.qty
        return res

    @api.multi
    def _get_remaining_qty(self):
        for ops in self:
            ops.remaining_qty = 0
            if ops.package_id and not ops.product_id:
                #dont try to compute the remaining quantity for packages because it's not relevant (a package could include different products).
                #should use _get_remaining_prod_quantities instead
                continue
            else:
                qty = ops.product_qty
                if ops.product_uom_id:
                    qty = self.env['product.uom']._compute_qty_obj(ops.product_uom_id, ops.product_qty, ops.product_id.uom_id)
                for record in ops.linked_move_operation_ids:
                    qty -= record.qty
                ops.remaining_qty = float_round(qty, precision_rounding=ops.product_id.uom_id.rounding)

    @api.onchange("product_id")
    def product_id_change(self):
        res = {}
        self.on_change_tests()
        if self.product_id and not self.product_uom_id or self.product_uom_id.category_id.id != self.product_id.uom_id.category_id.id:
            self.product_uom_id = self.product_id.uom_id.id
        if self.product_id:
            self.lots_visible = (self.product_id.tracking != 'none')
            res['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        return res

    @api.multi
    def on_change_tests(self):
        if self.product_id:
            product = self.product_id
            self.product_uom_id = self.product_uom_id or self.product_id.uom_id.id
            # selected_uom = product_uom_id
            if self.product_uom_id.category_id.id != self.product_id.uom_id.category_id.id:
                raise UserError(_('Warning: wrong UoM!'), _('The selected UoM for product %s is not compatible with the UoM set on the product form. \nPlease choose an UoM within the same UoM category.') % (self.product_id.name))

            if self.product_qty:
                rounded_qty = self.env['product.uom']._compute_qty(self.product_uom_id, self.product_qty, self.product_uom_id, round=True)
                if rounded_qty != self.product_qty:
                    raise UserError(_('Warning: wrong quantity!'), _('The chosen quantity for product %s is not compatible with the UoM rounding. It will be automatically converted at confirmation') % (product.name))

    @api.multi
    def _compute_location_description(self):
        for op in self:
            from_name = op.location_id.name
            to_name = op.location_dest_id.name
            if op.package_id and op.product_id:
                from_name += " : " + op.package_id.name
            if op.result_package_id:
                to_name += " : " + op.result_package_id.name
            op.from_loc = from_name,
            op.to_loc = to_name

    @api.multi
    def _get_bool(self):
        for pack in self:
            pack.processed_boolean = (pack.qty_done > 0.0)

    @api.multi
    def _set_processed_qty(self, field_value):
        if not self.product_id:
            if field_value and self.qty_done == 0:
                self.write({'qty_done': 1.0})
            if not field_value and self.qty_done != 0:
                self.write({'qty_done': 0.0})
        return True

    @api.multi
    def _compute_lots_visible(self):
        for pack in self:
            if pack.pack_lot_ids:
                continue
            product_requires = (pack.product_id.tracking != 'none')
            if pack.picking_id.picking_type_id:
                pack.lots_visible = (pack.picking_id.picking_type_id.use_existing_lots or pack.picking_id.picking_type_id.use_create_lots) and product_requires
            else:
                pack.lots_visible = product_requires

    @api.model
    def _get_default_from_loc(self):
        default_loc = self.env.context.get('default_location_id')
        if default_loc:
            return self.env['stock.location'].browse(default_loc).name

    @api.model
    def _get_default_to_loc(self):
        default_loc = self.env.context.get('default_location_dest_id')
        if default_loc:
            return self.env['stock.location'].browse(default_loc).name

    picking_id = fields.Many2one('stock.picking', 'Stock Picking', help='The stock operation where the packing has been made', required=True)
    product_id = fields.Many2one('product.product', 'Product', ondelete="CASCADE")  # 1
    product_uom_id = fields.Many2one('product.uom', 'Unit of Measure')
    product_qty = fields.Float('To Do', digits_compute=dp.get_precision('Product Unit of Measure'), required=True, default=0.0)
    qty_done = fields.Float('Processed', digits_compute=dp.get_precision('Product Unit of Measure'), default=0.0)
    processed_boolean = fields.Boolean(compute="_get_bool", fnct_inv=_set_processed_qty, string='Processed', default=lambda *a: False)
    package_id = fields.Many2one('stock.quant.package', 'Source Package')  # 2
    pack_lot_ids = fields.One2many('stock.pack.operation.lot', 'operation_id', 'Lots Used')
    result_package_id = fields.Many2one('stock.quant.package', 'Destination Package', help="If set, the operations are packed into this package", required=False, ondelete='cascade')
    date = fields.Datetime(required=True, default=fields.Date.today())
    owner_id = fields.Many2one('res.partner', 'Owner', help="Owner of the quants")
    #'update_cost': fields.boolean('Need cost update'),
    linked_move_operation_ids = fields.One2many('stock.move.operation.link', 'operation_id', string='Linked Moves', readonly=True, help='Moves impacted by this operation for the computation of the remaining quantities')
    remaining_qty = fields.Float(compute="_get_remaining_qty", digits=0, string="Remaining Qty", help="Remaining quantity in default UoM according to moves matched with this operation. ")
    location_id = fields.Many2one('stock.location', 'Source Location', required=True)
    location_dest_id = fields.Many2one('stock.location', 'Destination Location', required=True)
    picking_source_location_id = fields.Many2one(related='picking_id.location_id', relation='stock.location')
    picking_destination_location_id = fields.Many2one(related='picking_id.location_dest_id', relation='stock.location')
    from_loc = fields.Char(compute="_compute_location_description", string='From', multi='loc', default=_get_default_from_loc)
    to_loc = fields.Char(compute="_compute_location_description", string='To', multi='loc', default=_get_default_to_loc)
    fresh_record = fields.Boolean('Newly created pack operation', default=True)
    lots_visible = fields.Boolean(compute="_compute_lots_visible")
    state = fields.Selection(related='picking_id.state', selection=[
            ('draft', 'Draft'),
            ('cancel', 'Cancelled'),
            ('waiting', 'Waiting Another Operation'),
            ('confirmed', 'Waiting Availability'),
            ('partially_available', 'Partially Available'),
            ('assigned', 'Available'),
            ('done', 'Done'),
            ])

    @api.multi
    def split_quantities(self):
        for pack in self:
            if pack.product_qty - pack.qty_done > 0.0 and pack.qty_done < pack.product_qty:
                pack2 = pack.copy(default={'qty_done': 0.0, 'product_qty': pack.product_qty - pack.qty_done})
                pack.write({'product_qty': pack.qty_done})
            else:
                raise UserError(_('The quantity to split should be smaller than the quantity To Do.  '))
        return True

    @api.multi
    def write(self, vals):
        vals['fresh_record'] = False
        res = super(StockPackOperation, self).write(vals)
        return res

    @api.multi
    def unlink(self):
        if any([x.state in ('done', 'cancel') for x in self]):
            raise UserError(_('You can not delete pack operations of a done picking'))
        return super(StockPackOperation, self).unlink()

    @api.multi
    def check_tracking(self):
        """ Checks if serial number is assigned to stock move or not and raise an error if it had to.
        """
        for ops in self:
            if ops.picking_id and (ops.picking_id.picking_type_id.use_existing_lots or ops.picking_id.picking_type_id.use_create_lots) and \
            ops.product_id and ops.product_id.tracking != 'none' and ops.qty_done > 0.0:
                if not ops.pack_lot_ids:
                    raise UserError(_('You need to provide a Lot/Serial Number for product %s') % ops.product_id.name)
                if ops.product_id.tracking == 'serial':
                    for opslot in ops.pack_lot_ids:
                        if opslot.qty not in (1.0, 0.0):
                            raise UserError(_('You should provide a different serial number for each piece'))

    @api.multi
    def save(self):
        for pack in self:
            if pack.product_id.tracking != 'none':
                qty_done = sum([x.qty for x in pack.pack_lot_ids])
                pack.write({'qty_done': qty_done})
        return {'type': 'ir.actions.act_window_close'}

    @api.multi
    def split_lot(self):
        assert len(self) > 0
        pack = self[0]
        picking_type = pack.picking_id.picking_type_id
        serial = (pack.product_id.tracking == 'serial')
        view = self.env.ref('stock.view_pack_operation_lot_form').id
        only_create = picking_type.use_create_lots and not picking_type.use_existing_lots
        show_reserved = any([x for x in pack.pack_lot_ids if x.qty_todo > 0.0])

        self.with_context({'serial': serial,
                    'only_create': only_create,
                    'create_lots': picking_type.use_create_lots,
                    'state_done': pack.picking_id.state == 'done',
                    'show_reserved': show_reserved})
        return {
                'name': _('Lot Details'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.pack.operation',
                'views': [(view, 'form')],
                'view_id': view,
                'target': 'new',
                'res_id': pack.id,
                'context': self.env.context,
            }

    @api.multi
    def show_details(self):
        view = self.env.ref('stock.view_pack_operation_details_form_save').id
        return {
                'name': _('Operation Details'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'stock.pack.operation',
                'views': [(view, 'form')],
                'view_id': view,
                'target': 'new',
                'res_id': self[0].id,
                'context': self.env.context,
        }

    @api.onchange('pack_lot_ids')
    def _onchange_packlots(self):
        self.qty_done = sum([x.qty for x in self.pack_lot_ids])
