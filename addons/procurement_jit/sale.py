# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.multi
    def _action_procurement_create(self):
        res = super(SaleOrderLine, self)._action_procurement_create()
        orders = list(set(x.order_id for x in self))
        for order in orders:
            order.picking_ids.filtered(lambda x: x.state=='confirmed' and not x.quant_reserved_exist).action_assign()
            reassign = order.picking_ids.filtered(lambda x: not x.printed and x.state=='partially_available' or ((x.state=='confirmed') and x.quant_reserved_exist))
            if reassign:
                reassign.do_unreserve()
                reassign.action_assign()
        return res