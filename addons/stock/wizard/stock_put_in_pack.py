# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError

class stock_put_in_pack(models.TransientModel):
    _name = 'stock.put.in.pack'
    _description = 'Put in Pack wizard'

    picking_id = fields.Many2one('stock.picking', 'Picking')
    package_id = fields.Many2one('stock.quant.package', 'Package')
    name = fields.Text('Package Name')

    @api.model
    def default_get(self, fields):
        res = {}
        active_id = self._context.get('active_id')
        if active_id:
            package_id = self._context.get('pack_id')
            package = self.env['stock.quant.package'].browse(package_id)

            res = {
                'picking_id': active_id,
                'package_id': package_id,
                'name': package.name
            }
        return res

    @api.multi
    def process(self):
        self.ensure_one()
        if self.name != self.package_id.name:
            self.package_id.name = self.name
        return {}

