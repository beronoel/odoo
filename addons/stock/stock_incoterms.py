# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

#----------------------------------------------------------
# Incoterms
#----------------------------------------------------------
class StockIncoterms(models.Model):
    _name = "stock.incoterms"
    _description = "Incoterms"

    name = fields.Char(required=True, help="Incoterms are series of sales terms. They are used to divide transaction costs and responsibilities between buyer and seller and reflect state-of-the-art transportation practices.")
    code = fields.Char(required=True, help="Incoterm Standard Code")
    active = fields.Boolean(default=True, help="By unchecking the active field, you may hide an INCOTERM you will not use.")
