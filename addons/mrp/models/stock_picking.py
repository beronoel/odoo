# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    code = fields.Selection(selection_add=[('mrp_operation', 'Manufacturing Operation')])
    count_mo_todo = fields.Integer(compute='_get_mo_count')
    count_mo_waiting = fields.Integer(compute='_get_mo_count')
    count_mo_late = fields.Integer(compute='_get_mo_count')

    def _get_mo_count(self):
        # TDE FIXME: use fields.Datetime
        MrpProduction = self.env['mrp.production']
        for picking in self:
            if picking.code == 'mrp_operation':
                picking.count_mo_waiting = MrpProduction.search_count([('availability', '=', 'waiting')])
                picking.count_mo_todo = MrpProduction.search_count([('state', 'in', ('confirmed', 'planned', 'progress'))])
                picking.count_mo_late = MrpProduction.search_count(['&', ('date_planned', '<', datetime.now().strftime('%Y-%m-%d')), ('state', '=', 'confirmed')])
