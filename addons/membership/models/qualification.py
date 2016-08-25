# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError
import dateutil.relativedelta as relativedelta
import logging

_logger = logging.getLogger(__name__)


class Partner(models.Model):
    _inherit = 'res.partner'
    
    qualification_lines = fields.Many2many('membership.qualification_line', 'partner', string='Qualification')


class Qualification(models.Model):
    _name = 'membership.qualification'
    
    name = fields.Char(string='Identifier')
    machines = fields.Many2many(comodel_name='hr.equipment', relation='equipment_qualification', column1='qualification_id', column2='equipment_id', string='Machines')
    duration = fields.Integer(string='Duration (month)')

    
class QualificationLine(models.Model):
    _name = 'membership.qualification_line'
    
    partner = fields.Many2one('res.partner')
    qualification = fields.Many2one('membership.qualification',
                                    required=True)
    qualification_date_from = fields.Date(string='Qualification Start Date', 
                                          help='Date from which qualification becomes valid.',
                                          default=fields.Date.today())
    qualification_date_to = fields.Date(string='Qualification End Date', 
                                        help='Date until which qualification remains valid.')
    valid = fields.Boolean(compute='compute_valid',
                           default=True)

    note = fields.Char(string='Note',
                       help='Comments on qualification')
    
    @api.onchange('qualification_date_from')
    def check_change(self):
        self.compute_qualification_date_to()
    
    @api.model
    def create(self, values):
        record = super(QualificationLine, self).create(values)
        
        for line in record.partner.qualification_lines:
            _logger.debug(line.qualification)
            _logger.debug(record.qualification)
            _logger.debug("")
            
        _logger.debug("WOW")
        
        record.qualification_date_from = fields.Date.today()
        record.compute_qualification_date_to()
        
        return record
    
    @api.one
    def compute_valid(self):
        date_to = self.qualification_date_to
        today = fields.Date.today()
        
        if today < date_to:
            self.valid = True
        else:
            self.valid = False
    
    @api.one
    def renew_qualification(self):
        self.qualification_date_from = fields.Date.today()
        self.compute_qualification_date_to()
            
    def compute_qualification_date_to(self):
        date_from = fields.Date.from_string(self.qualification_date_from)
        date_to = date_from + relativedelta.relativedelta(months=self.qualification.duration)
        self.qualification_date_to = fields.Date.to_string(date_to)

