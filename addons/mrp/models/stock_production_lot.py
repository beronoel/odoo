# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class StockProductionLot(models.Model):
    _inherit = "stock.production.lot"

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        # TDE FIXME: perf + usefull + wtf ?
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), '|', ('quant_ids.consumed_quant_ids.lot_id.name', operator, name), ('quant_ids.produced_quant_ids.lot_id.name', operator, name)]
        pos = self.search(domain + args, limit=limit)
        return pos.name_get()
