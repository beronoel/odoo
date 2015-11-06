# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import openerp.addons.decimal_precision as dp
from openerp import api, fields, models
from openerp.tools.translate import _
from openerp.exceptions import UserError
from openerp.tools import float_round


class MrpBom(models.Model):
    """
    Defines bills of material for a product.
    """
    _inherit = 'mrp.bom'

    routing_id = fields.Many2one('mrp.routing', string='Routing')

    def get_operation_lines(self):
        if self.routing_id:
            return self.routing_id.workcenter_line_ids
        return super(MrpBom, self).get_operation_lines()

