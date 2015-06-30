# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time

from openerp import _, api, fields, models
from openerp.exceptions import UserError


class HrAttendanceError(models.TransientModel):

    _name = 'hr.attendance.error'
    _description = 'Print Error Attendance Report'

    init_date = fields.Date(string='Starting Date', required=True,
                            default=lambda *val: time.strftime('%Y-%m-%d'))
    end_date = fields.Date(string='Ending Date', required=True,
                           default=lambda *val: time.strftime('%Y-%m-%d'))
    max_delay = fields.Integer(string='Max. Delay (Min)', required=True,
                               default=120)

    @api.multi
    def print_report(self):
        emp_ids = []
        data_error = self.read()[0]
        date_from = data_error['init_date']
        date_to = data_error['end_date']
        self.env.cr.execute("SELECT id FROM hr_attendance WHERE employee_id IN %s AND to_char(name, 'YYYY-mm-dd')<=%s AND to_char(name, 'YYYY-mm-dd')>=%s AND action IN %s ORDER BY name", (tuple(self.env.context['active_ids']), date_to, date_from, tuple(['sign_in', 'sign_out'])))
        attendance_ids = [x[0] for x in self.env.cr.fetchall()]
        if not attendance_ids:
            raise UserError(_('No records are found for your selection!'))
        attendance_records = self.env['hr.attendance'].browse(attendance_ids)
        for rec in attendance_records:
            if rec.employee_id.id not in emp_ids:
                emp_ids.append(rec.employee_id.id)
        data_error['emp_ids'] = emp_ids
        datas = {'ids': [], 'model': 'hr.employee', 'form': data_error}

        return self.env['report'].get_action(self, 'hr_attendance.report_attendanceerrors', data=datas)
