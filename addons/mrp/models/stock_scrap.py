# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    production_id = fields.Many2one('mrp.production', 'Manufacturing Order', 
                                    states={'done': [('readonly', True)]})
    workorder_id = fields.Many2one('mrp.workorder', 
                                   states={'done': [('readonly', True)]}) #Not to restrict/prefer quants, but informative

    def _prepare_move(self):
        self.ensure_one()
        vals = super(StockScrap, self)._prepare_move()
        if self.production_id:
            if self.product_id in self.production_id.move_finished_ids.mapped('product_id').ids:
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
                preferred_domain_list = [preferred_domain, preferred_domain2, preferred_domain3]
            elif self.product_id in self.production_id.move_finished_ids.mapped('product_id'):
                preferred_domain = [('history_ids', 'in', self.production_id.move_finished_ids.ids)]
                preferred_domain2 = [('history_ids', 'not in', self.production_id.move_finished_ids.ids)]
                preferred_domain_list = [preferred_domain, preferred_domain2]
        else:
            preferred_domain_list = super(StockScrap, self)._get_preferred_domain()
        return preferred_domain_list

    @api.model
    def default_get(self, fields):
        rec = super(StockScrap, self).default_get(fields)
        context = dict(self._context or {})
        if context.get('active_model') == 'mrp.production' and context.get('active_id'):
            production = self.env['mrp.production'].browse(context['active_id'])
            rec.update({
                        'production_id': production.id,
                        'origin': production.name,
                        'location_id': production.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')) and production.location_src_id.id or production.location_dest_id.id,
                        })
        elif context.get('active_model') == 'mrp.workorder' and context.get('active_id'):
            workorder = self.env['mrp.workorder'].browse(context['active_id'])
            rec.update({
                        'production_id': workorder.production_id.id,
                        'workorder_id': workorder.id,
                        'origin': workorder.production_id.name,
                        'location_id': workorder.production_id.location_src_id.id,
                        })
        return rec