# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.multi
    def _action_procurement_create(self):
        res = super(SaleOrder, self)._action_procurement_create()
        for order in self:
            order.picking_ids.filtered(lambda x: x.state=='confirmed').action_assign()
            reassign = order.picking_ids.filtered(lambda x: x.state=='partially_available')
            if reassign:
                reassign.do_unreserve()
                reassign.action_assign()
        return res