# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class Employee(models.Model):

    _inherit = 'hr.employee'

    goal_ids = fields.One2many('gamification.goal', string='Employee HR Goals', compute='_compute_employee_goals')
    badge_ids = fields.One2many('gamification.badge.user', string='Employee Badges', compute='_compute_employee_badges')
    has_badges = fields.Boolean('Has badges', compute='_compute_has_badges')

    @api.multi
    def _compute_employee_goals(self):
        user_ids = self.mapped('user_id').ids
        goals = self.env['gamification.goal'].search([
            ('user_id', 'in', user_ids),
            ('challenge_id.category', '=', 'hr')
        ])
        for employee in self:
            employee.goal_ids = goals.filtered(lambda goal: goal.user_id == employee.user_id)

    @api.multi
    def _compute_employee_badges(self):
        """ Return the list of badge_users assigned to the employee """
        for employee in self:
            employee.badge_ids = self.env['gamification.badge.user'].search([
                '|',
                    ('employee_id', '=', employee.id),
                    '&',
                        ('employee_id', '=', False),
                        ('user_id', '=', employee.user_id.id)
                ])

    @api.multi
    def _compute_has_badges(self):
        employee_data = self.env['gamification.badge.user'].read_group([('employee_id', 'in', self.ids)], ['employee_id'], ['employee_id'])
        mapped_employee_data = dict([(m['employee_id'][0], m['employee_id_count']) for m in employee_data])

        user_data = self.env['gamification.badge.user'].read_group([('employee_id', '=', False), ('user_id', 'in', self.mapped('user_id').ids)], ['user_id'], ['user_id'])
        mapped_user_data = dict([(m['user_id'][0], m['user_id_count']) for m in user_data])

        for employee in self:
            employee.has_badges = bool(mapped_employee_data.get(employee.id, 0) + mapped_user_data.get(employee.id, 0))
