# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class WebsiteCrmConfigSettings(models.TransientModel):
    _inherit = 'website.config.settings'

    user_id = fields.Many2one('res.users', string='Salesperson', related='website_id.crm_user_id')
    team_id = fields.Many2one('crm.team', string='Sales Team', related='website_id.crm_team_id', domain=lambda self: self.env.user.has_group('crm.group_use_lead') and [('use_leads','=', True)] or [('use_opportunities','=', True)])
