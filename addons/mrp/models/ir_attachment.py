# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

AVAILABLE_PRIORITIES = [
    ('0', 'Normal'),
    ('1', 'Low'),
    ('2', 'High'),
    ('3', 'Very High'),
]


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'
    _order = "priority desc"

    #  TDE FIXME: I really don't like having a priority on attachments. Maybe starring it.
    priority = fields.Selection(AVAILABLE_PRIORITIES, help="Gives the sequence order when displaying a list of tasks.")
