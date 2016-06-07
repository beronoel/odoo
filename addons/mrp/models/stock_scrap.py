# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    production_id = fields.Many2one(
        'mrp.production', 'Manufacturing Order',
        states={'done': [('readonly', True)]})
    workorder_id = fields.Many2one(
        'mrp.workorder', 'Work Order',
        states={'done': [('readonly', True)]},
        help='Not to restruct or prefer quants, but informative.')

    @api.onchange('workorder_id')
    def _onchange_workorder_id(self):
        self.production_id = self.workorder_id.production_id.id,
        self.location_id = self.workorder_id.production_id.location_src_id.id

    @api.onchange('production_id')
    def _onchange_production_id(self):
        self.origin = self.production_id.name
        if not self.location_id:
            self.location_id = self.production_id.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')) and self.production_id.location_src_id.id or self.production_id.location_dest_id.id,

    def _get_default_values_from_onchanges(self, vals):
        res = dict(vals)
        _onchanges = [
            ('workorder_id', '_onchange_workorder_id', ['production_id', 'location_id']),
            ('production_id', '_onchange_production_id', ['origin', 'location_id'])
        ]
        for field_name, method_name, result_field_name in _onchanges:
            if field_name not in res:
                continue
            scrap = self.new(res)
            getattr(scrap, method_name)()
            scrap_values = scrap._convert_to_write(scrap._cache)
            for field in [f for f in result_field_name if f in scrap_values]:
                res[field] = scrap_values[field]
        return res

    @api.model
    def create(self, vals):
        vals = self._get_default_values_from_onchanges(vals)
        return super(StockScrap, self).create(vals)

    def _prepare_move_values(self):
        self.ensure_one()
        vals = super(StockScrap, self)._prepare_move_values()
        if self.production_id:
            if self.product_id in self.production_id.move_finished_ids.mapped('product_id'):
                vals['production_id'] = self.production_id.id
            else:
                vals['raw_material_production_id'] = self.production_id.id
        return vals

    def _get_preferred_domain(self):
        if self.production_id:
            if self.product_id in self.production_id.move_raw_ids.mapped('product_id'):
                preferred_domain = [('reservation_id', 'in', self.production_id.move_raw_ids.ids)]
                preferred_domain2 = [('reservation_id', '=', False)]
                preferred_domain3 = ['&', ('reservation_id', 'not in', self.production_id.move_raw_ids.ids), ('reservation_id', '!=', False)]
                return [preferred_domain, preferred_domain2, preferred_domain3]
            elif self.product_id in self.production_id.move_finished_ids.mapped('product_id'):
                preferred_domain = [('history_ids', 'in', self.production_id.move_finished_ids.ids)]
                preferred_domain2 = [('history_ids', 'not in', self.production_id.move_finished_ids.ids)]
                return [preferred_domain, preferred_domain2]
        return super(StockScrap, self)._get_preferred_domain()
