# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import fields, models


class MrpRouting(models.Model):
    """
    For specifying the routings of Work Centers.
    """
    _name = 'mrp.routing'

    _description = 'Routings'
    name = fields.Char(required=True)
    active = fields.Boolean(default=True, help="If the active field is set to False, it will allow you to hide the routing without removing it.")
    code = fields.Char()
    note = fields.Text(string='Description')
    workcenter_line_ids = fields.One2many('mrp.routing.workcenter', 'routing_id', string='Work Centers', copy=True, oldname='workcenter_lines')

    location_id = fields.Many2one('stock.location', string='Production Location',
                                  help="Keep empty if you produce at the location where the finished products are needed."
                                  "Set a location if you produce at a fixed location. This can be a partner location "
                                  "if you subcontract the manufacturing operations.")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env['res.company']._company_default_get('mrp.routing'))


class MrpRoutingWorkcenter(models.Model):
    """
    Defines working cycles and hours of a Work Center using routings.
    """
    _inherit = 'mrp.routing.workcenter'

    routing_id = fields.Many2one('mrp.routing', string='Parent Routing', index=True, ondelete='cascade',
                                 help="Routings indicates all the Work Centers used, for how long and/or cycles."
                                 "If Routings is indicated then,the third tab of a production order (Work Centers) will be automatically pre-completed.")
