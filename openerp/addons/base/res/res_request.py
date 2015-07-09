# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models


@api.multi
def referencable_models(self):
    ResRequestLink = self.env['res.request.link']
    res = ResRequestLink.read(ResRequestLink.search([]), ['object', 'name'])
    return [(r['object'], r['name']) for r in res]


class ResRequestLink(models.Model):
    _name = 'res.request.link'
    _order = 'priority'

    name = fields.Char(required=True, translate=True)
    object = fields.Char(required=True)
    priority = fields.Integer(default=5)
