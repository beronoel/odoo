# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AccountConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    plafond_secu = fields.Float(related='company_id.plafond_secu', default=lambda self: self.env.user.company_id.plafond_secu)
    nombre_employes = fields.Integer(related='company_id.nombre_employes', default=lambda self: self.env.user.company_id.nombre_employes)
    cotisation_prevoyance = fields.Float(related='company_id.cotisation_prevoyance', default=lambda self: self.env.user.company_id.cotisation_prevoyance)
    org_ss = fields.Char(related='company_id.org_ss', default=lambda self: self.env.user.company_id.org_ss)
    conv_coll = fields.Char(related='company_id.conv_coll', default=lambda self: self.env.user.company_id.conv_coll)

