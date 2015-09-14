# -*- encoding: utf-8 -*-
from openerp import models, fields

class website_config_settings(models.TransientModel):
    _inherit = 'website.config.settings'

    salesperson_id = fields.Many2one('res.users', related='website_id.salesperson_id', string='Salesperson')
    salesteam_id = fields.Many2one('crm.team', related='website_id.salesteam_id', string='Sales Team')
    shipping_integration = fields.Selection([
            (0, "Do not activate the shipping integration"),
            (1, "Activate the shipping integration"),
            ], "Shipping Integration")
    ebay_connector = fields.Selection([
            (0, "Do not activate the eBay connector"),
            (1, "Activate the eBay connector"),
            ], "eBay connector")
    amazon_connector = fields.Selection([
            (0, "Do not activate the Amazon connector"),
            (1, "Activate the Amazon connector"),
            ], "Shipping Integration")
    coupons = fields.Selection([
            (0, "Do not activate coupons"),
            (1, "Activate coupons"),
            ], "Coupons")
