# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import fields, models


class WebsiteConfigSettings(models.TransientModel):
    _inherit = 'website.config.settings'

    salesperson_id = fields.Many2one('res.users', related='website_id.salesperson_id', string='Salesperson')
    salesteam_id = fields.Many2one('crm.team', related='website_id.salesteam_id', string='Sales Team')
