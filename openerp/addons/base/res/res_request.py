# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models


@api.model
def referencable_models(self):
    records = self.env['res.request.link'].search([]).read(['object', 'name'])
    return [(record['object'], record['name']) for record in records]


class ResRequestLink(models.Model):
    _name = 'res.request.link'
    _order = 'priority'

    name = fields.Char(required=True, translate=True)
    object = fields.Char(required=True)
    priority = fields.Integer(default=5)
