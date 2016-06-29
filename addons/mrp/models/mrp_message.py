# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import html2plaintext


class MrpProductionMessage(models.Model):
    _name = "mrp.message"
    _description = "Production Message"

    @api.model
    def _default_valid_until(self):
        return datetime.today() + relativedelta(days=7)

    name = fields.Text(compute='_get_note_first_line', store=True)
    message = fields.Html(required=True)
    product_id = fields.Many2one('product.product', string="Product")
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material', domain="[('product_id', '=', product_id)]")
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    valid_until = fields.Date('Validity Date', default=_default_valid_until, required=True)
    routing_id = fields.Many2one('mrp.routing', string='Routing')

    @api.depends('message')
    def _get_note_first_line(self):
        for message in self:
            message.name = (message.message and html2plaintext(message.message) or "").strip().replace('*', '').split("\n")[0]

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id)

    @api.multi
    def save(self):
        return True
