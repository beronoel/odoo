# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class Lead(models.Model):
    _inherit = 'crm.lead'

    def website_form_input_filter(self, request, values):
        values['medium_id'] = (
                values.get('medium_id') or
                self.default_get(['medium_id']).get('medium_id') or
                self.sudo().env['ir.model.data'].xmlid_to_res_id('utm.utm_medium_website')
        )
        values['user_id'] = request.website.crm_user_id.id
        values['team_id'] = request.website.crm_team_id.id
        return values


class Website(models.Model):
    _inherit = 'website'

    crm_user_id = fields.Many2one('res.users', string='Salesperson')
    crm_team_id = fields.Many2one('crm.team', string='Sales Team',
		default=lambda self: self.env['crm.team'].search([], limit=1))
