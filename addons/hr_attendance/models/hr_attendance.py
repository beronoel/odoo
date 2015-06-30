# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from openerp import _, api, fields, models
from openerp.exceptions import UserError


class HrActionReason(models.Model):
    _name = "hr.action.reason"
    _description = "Action Reason"

    name = fields.Char(string='Reason', required=True, help='Specifies the reason for Signing In/Signing Out.')
    action_type = fields.Selection([('sign_in', 'Sign in'), ('sign_out', 'Sign out')], string="Action Type", default='sign_in')


class HrAttendance(models.Model):
    _name = "hr.attendance"
    _description = "Attendance"
    _order = 'name desc'

    def _employee_get(self):
        ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        return ids and ids.id or False

    name = fields.Datetime(string='Date', required=True, select=True, default=fields.Datetime.now)
    action = fields.Selection([('sign_in', 'Sign In'), ('sign_out', 'Sign Out'), ('action', 'Action')], required=True)
    action_desc = fields.Many2one("hr.action.reason", string="Action Reason", domain="[('action_type', '=', action)]", help='Specifies the reason for Signing In/Signing Out in case of extra hours.')
    employee_id = fields.Many2one('hr.employee', string="Employee", select=True, required=True, default=_employee_get)
    department_id = fields.Many2one('hr.department', string="Department", related="employee_id.department_id")
    worked_hours = fields.Float(compute='_compute_worked_hours', string='Worked Hours', store=True)

    @api.depends('action')
    def _compute_worked_hours(self):
        """For each hr.attendance record of action sign-in: assign 0.
        For each hr.attendance record of action sign-out: assign number
        of hours since last sign-in.
        """
        for data in self:
            if data.action == 'sign_in':
                data.worked_hours = 0
            elif data.action == 'sign_out':
            # Get the associated sign-in
                last_signin = data.search([
                    ('employee_id', '=', data.employee_id.id),
                    ('name', '<', data.name), ('action', '=', 'sign_in')
                ], limit=1, order='name DESC')
                if last_signin:
                    # Compute time elapsed between sign-in and sign-out
                    last_signin_datetime = fields.Datetime.from_string(last_signin.name)
                    signout_datetime = fields.Datetime.from_string(data.name)
                    workedhours_datetime = (signout_datetime - last_signin_datetime)
                    data.worked_hours = ((workedhours_datetime.seconds) / 60) / 60.0
                else:
                    data.worked_hours = False

    @api.constrains('action')
    def _altern_si_so(self):
        """ Alternance sign_in/sign_out check.
            Previous (if exists) must be of opposite action.
            Next (if exists) must be of opposite action.
        """
        prev_atts = self.search([('employee_id', '=', self.employee_id.id), ('name', '<', self.name), ('action', 'in', ('sign_in', 'sign_out'))], limit=1, order='name DESC')
        next_atts = self.search([('employee_id', '=', self.employee_id.id), ('name', '>', self.name), ('action', 'in', ('sign_in', 'sign_out'))], limit=1, order='name ASC')
        if prev_atts and prev_atts.action == self.action:  # previous exists and is same action
            raise UserError('Error ! Sign in (resp. Sign out) must follow Sign out (resp. Sign in)')
        if next_atts and next_atts.action == self.action:  # next exists and is same action
            raise UserError('Error ! Sign in (resp. Sign out) must follow Sign out (resp. Sign in)')
        if (not prev_atts) and (not next_atts) and self.action != 'sign_in':  # first attendance must be sign_in
            raise UserError('Error ! Sign in (resp. Sign out) must follow Sign out (resp. Sign in)')


class HrEmployee(models.Model):
    _description = "Employee"
    _inherit = "hr.employee"

    state = fields.Selection([('absent', 'Absent'), ('present', 'Present')], compute='_state', string='Attendance')
    last_sign = fields.Datetime(compute='_last_sign', string='Last Sign')
    attendance_access = fields.Boolean(compute='_attendance_access', string='Attendance Access')

    @api.multi
    def _state(self):
        for data in self:
            data.state = 'absent'
            self.env.cr.execute('SELECT hr_attendance.action, hr_attendance.employee_id \
                FROM ( \
                    SELECT MAX(name) AS name, employee_id \
                    FROM hr_attendance \
                    WHERE action in (\'sign_in\', \'sign_out\') \
                    GROUP BY employee_id \
                ) AS foo \
                LEFT JOIN hr_attendance \
                    ON (hr_attendance.employee_id = foo.employee_id \
                        AND hr_attendance.name = foo.name) \
                WHERE hr_attendance.employee_id IN %s', (tuple(self.ids),))
            for res in self.env.cr.fetchall():
                data.state = res[0] == 'sign_in' and 'present' or 'absent'

    @api.one
    def _last_sign(self):
        self.env.cr.execute("""select max(name) as name
                            from hr_attendance
                            where action in ('sign_in', 'sign_out')
                            and employee_id = %s""", (self.id,))
        for res in self.env.cr.fetchall():
            self.last_sign = res[0]

    @api.one
    def _attendance_access(self):
        # this function field use to hide attendance button to singin/singout from menu
        self.attendance_access = self.env.user.has_group("base.group_hr_attendance")

    @api.one
    def _action_check(self, dt):
        self.env.cr.execute('SELECT MAX(name) FROM hr_attendance WHERE employee_id=%s', (self.id, ))
        res = self.env.cr.fetchone()
        return not (res and (res[0] >= (dt or datetime.now)))

    @api.one
    def attendance_action_change(self):
        action_date = self.env.context.get('action_date', False)
        action = self.env.context.get('action', False)
        hr_attendance = self.env['hr.attendance']
        warning_sign = {'sign_in': _('Sign In'), 'sign_out': _('Sign Out')}
        if not action:
            if self.state == 'present': action = 'sign_out'
            if self.state == 'absent': action = 'sign_in'
        if not self._action_check(action_date):
            raise UserError(_('You tried to %s with a date anterior to another event !\nTry to contact the HR Manager to correct attendances.') % (warning_sign[action],))
        vals = {'action': action, 'employee_id': self.id}
        if action_date:
            vals['name'] = action_date
        hr_attendance.create(vals)
        return True
