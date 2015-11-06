# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import fields, models


class MrpRoutingWorkcenter(models.Model):
    """
    Defines working cycles and hours of a Work Center using routings.
    """
    _name = 'mrp.routing.workcenter'
    _description = 'Work Center Usage'
    _order = 'sequence, id'

    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center', required=True)
    name = fields.Char(required=True)
    bom_id = fields.Many2one('mrp.bom', string="Bill of Material", required=True)
    sequence = fields.Integer(default=100, help="Gives the sequence order when displaying a list of operations.")
    cycle_nbr = fields.Float(string='Number of Cycles', required=True, default=1.0, help="Number of iterations this work center has to do in the specified operation of the BoM.")
    hour_nbr = fields.Float(string='Number of Hours', required=True, help="Time in hours for this Work Center to achieve the operation of the given BoM.")
    note = fields.Text(string='Description')
    company_id = fields.Many2one('res.company', related='workcenter_id.company_id', string='Company', store=True, readonly=True)
