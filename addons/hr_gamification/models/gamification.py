# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BadgeUser(models.Model):
    """ User having received a badge"""

    _inherit = 'gamification.badge.user'

    employee_id = fields.Many2one("hr.employee", string='Employee')

    @api.constrains('employee_id')
    def _check_employee_related_user(self):
        for badge in self:
            if badge.user_id and badge.employee_id:
                if badge.employee_id not in badge.user_id.employee_ids:
                    raise ValidationError(_('The selected employee does not correspond to the selected user.'))


class Badge(models.Model):

    _inherit = 'gamification.badge'

    granted_employees_count = fields.Integer('# of granted employees', compute='_compute_granted_employees_count')

    @api.multi
    def _compute_granted_employees_count(self):
        badge_data = self.env['gamification.badge.user'].read_group([('badge_id', 'in', self.ids), ('employee_id', '!=', False)], ['badge_id'], ['badge_id'])
        mapped_data = dict([(badge['badge_id'][0], badge['badge_id_count']) for badge in badge_data])
        for badge in self:
            badge.granted_employees_count = mapped_data.get(badge.id, 0)

    @api.multi
    def action_granted_employees(self):
        self.ensure_one()
        employee_ids = self.mapped('owner_ids.employee_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Granted Employees',
            'view_mode': 'kanban,tree,form',
            'view_type': 'form',
            'res_model': 'hr.employee',
            'domain': [('id', 'in', employee_ids)]
        }
