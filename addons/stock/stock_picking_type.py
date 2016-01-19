# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import time
import json

from odoo import fields, models, api, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class StockPickingType(models.Model):
    _name = "stock.picking.type"
    _description = "The picking type determines the picking view"
    _order = 'sequence'

    @api.multi
    def open_barcode_interface(self):
        final_url = "/stock/barcode/#action=stock.ui&picking_type_id=" + str(self.ids[0]) if len(self.ids) else '0'
        return {'type': 'ir.actions.act_url', 'url': final_url, 'target': 'self'}

    @api.multi
    def _get_tristate_values(self):
        for picking_type_id in self:
            #get last 10 pickings of this type
            picking_ids = self.env['stock.picking'].search([('picking_type_id', '=', picking_type_id.id), ('state', '=', 'done')], order='date_done desc', limit=10)
            tristates = []
            for picking in picking_ids:
                if picking.date_done > picking.date:
                    tristates.insert(0, {'tooltip': picking.name or '' + ": " + _('Late'), 'value': -1})
                elif picking.backorder_id:
                    tristates.insert(0, {'tooltip': picking.name or '' + ": " + _('Backorder exists'), 'value': 0})
                else:
                    tristates.insert(0, {'tooltip': picking.name or '' + ": " + _('OK'), 'value': 1})
            picking_type_id.last_done_picking = json.dumps(tristates)

    @api.multi
    def _get_picking_count(self):
        obj = self.env['stock.picking']
        domains = {
            'count_picking_draft': [('state', '=', 'draft')],
            'count_picking_waiting': [('state', 'in', ('confirmed', 'waiting'))],
            'count_picking_ready': [('state', 'in', ('assigned', 'partially_available'))],
            'count_picking': [('state', 'in', ('assigned', 'waiting', 'confirmed', 'partially_available'))],
            'count_picking_late': [('min_date', '<', time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)), ('state', 'in', ('assigned', 'waiting', 'confirmed', 'partially_available'))],
            'count_picking_backorders': [('backorder_id', '!=', False), ('state', 'in', ('confirmed', 'assigned', 'waiting', 'partially_available'))],
        }
        result = {}
        for field in domains:
            data = obj.read_group(domains[field] +
                [('state', 'not in', ('done', 'cancel')), ('picking_type_id', 'in', self.ids)],
                ['picking_type_id'], ['picking_type_id'])
            count = dict(map(lambda x: (x['picking_type_id'] and x['picking_type_id'][0], x['picking_type_id_count']), data))
            for tid in self.ids:
                result.setdefault(tid, {})[field] = count.get(tid, 0)
        for tid in self:
            if result[tid]['count_picking']:
                tid.rate_picking_late = result[tid]['count_picking_late'] * 100 / result[tid]['count_picking']
                tid.rate_picking_backorders = result[tid]['count_picking_backorders'] * 100 / result[tid]['count_picking']
            else:
                tid.rate_picking_late = 0
                tid.rate_picking_backorders = 0
            tid.count_picking_draft = result[tid.id]['count_picking_draft']
            tid.count_picking_waiting = result[tid.id]['count_picking_waiting']
            tid.count_picking_ready = result[tid.id]['count_picking_ready']
            tid.count_picking = result[tid.id]['count_picking']
            tid. count_picking_late = result[tid.id]['count_picking_late']
            tid.count_picking_backorders = result[tid.id]['count_picking_backorders']

    @api.multi
    def _get_action(self, action):
        result = self.env.ref(action, raise_if_not_found=True)
        result = result.read()[0]
        if self:
            result.display_name = self.display_name
        return result

    @api.multi
    def get_action_picking_tree_late(self):
        return self._get_action('stock.action_picking_tree_late')

    @api.multi
    def get_action_picking_tree_backorder(self):
        return self._get_action('stock.action_picking_tree_backorder')

    @api.multi
    def get_action_picking_tree_waiting(self):
        return self._get_action('stock.action_picking_tree_waiting')

    @api.multi
    def get_action_picking_tree_ready(self):
        return self._get_action('stock.action_picking_tree_ready')

    @api.onchange('code')
    def onchange_picking_code(self):
        if not self.code:
            return False
        stock_loc = self.env.ref('stock.stock_location_stock').id
        self.default_location_src_id = stock_loc
        self.default_location_dest_id = stock_loc
        if self.code == 'incoming':
            self.default_location_src_id = self.env.ref('stock.stock_location_suppliers')
        elif self.code == 'outgoing':
            self.default_location_dest_id = self.env.ref('stock.stock_location_customers')

    @api.multi
    def _get_name(self):
        return dict(self.name_get())

    @api.multi
    def name_get(self):
        """Overides orm name_get method to display 'Warehouse_name: PickingType_name' """
        res = []
        if not self.ids:
            return res
        for record in self:
            name = record.name
            if record.warehouse_id:
                name = record.warehouse_id.name + ': ' + name
            if self.env.context.get('special_shortened_wh_name'):
                if record.warehouse_id:
                    name = record.warehouse_id.name
                else:
                    name = _('Customer') + ' (' + record.name + ')'
            res.append((record.id, name))
        return res

    @api.model
    def _default_warehouse(self):
        res = self.env['stock.warehouse'].search([('company_id', '=', self.env.user.company_id.id)], limit=1)
        return res and res[0] or False

    name = fields.Char('Picking Type Name', translate=True, required=True)
    complete_name = fields.Char(compute="_get_name", string='Name')
    color = fields.Integer()
    sequence = fields.Integer(help="Used to order the 'All Operations' kanban view")
    sequence_id = fields.Many2one('ir.sequence', 'Reference Sequence', required=True)
    default_location_src_id = fields.Many2one('stock.location', 'Default Source Location', help="This is the default source location when you create a picking manually with this picking type. It is possible however to change it or that the routes put another location. If it is empty, it will check for the supplier location on the partner. ")
    default_location_dest_id = fields.Many2one('stock.location', 'Default Destination Location', help="This is the default destination location when you create a picking manually with this picking type. It is possible however to change it or that the routes put another location. If it is empty, it will check for the customer location on the partner. ")
    code = fields.Selection([('incoming', 'Suppliers'), ('outgoing', 'Customers'), ('internal', 'Internal')], 'Type of Operation', required=True)
    return_picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type for Returns')
    show_entire_packs = fields.Boolean('Allow moving packs', help="If checked, this shows the packs to be moved as a whole in the Operations tab all the time, even if there was no entire pack reserved.")
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', ondelete='cascade', default=_default_warehouse)
    active = fields.Boolean(default=True)
    use_create_lots = fields.Boolean('Create New Lots', help="If this is checked only, it will suppose you want to create new Serial Numbers / Lots, so you can provide them in a text field. ")
    use_existing_lots = fields.Boolean('Use Existing Lots', help="If this is checked, you will be able to choose the Serial Number / Lots. You can also decide to not put lots in this picking type.  This means it will create stock with no lot or not put a restriction on the lot taken. ")
    # Statistics for the kanban view
    last_done_picking = fields.Char(compute="_get_tristate_values", string='Last 10 Done Pickings')
    count_picking_draft = fields.Integer(compute="_get_picking_count")
    count_picking_ready = fields.Integer(compute="_get_picking_count")
    count_picking = fields.Integer(compute="_get_picking_count")
    count_picking_waiting = fields.Integer(compute="_get_picking_count")
    count_picking_late = fields.Integer(compute="_get_picking_count")
    count_picking_backorders = fields.Integer(compute="_get_picking_count")
    rate_picking_late = fields.Integer(compute="_get_picking_count")
    rate_picking_backorders = fields.Integer(compute="_get_picking_count")
    # Barcode nomenclature
    barcode_nomenclature_id = fields.Many2one('barcode.nomenclature', 'Barcode Nomenclature', help='A barcode nomenclature')
