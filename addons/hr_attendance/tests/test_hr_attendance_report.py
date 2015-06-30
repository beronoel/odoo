# -*- coding: utf-8 -*-

import time
from openerp.tests import common
from openerp.tools import test_reports


class TestHrAttendanceReport(common.TransactionCase):

    def setUp(self):
        super(TestHrAttendanceReport, self).setUp()

        self.HrEmployee = self.env['hr.employee']
        self.hr_employee_fp = self.env.ref('hr.employee_fp')

    def test_hr_attendance_report(self):
        # Print HR Attendance Error Report through the wizard
        ctx = {'model': 'hr.employee', 'active_ids': [self.hr_employee_fp.id]}
        data_dict = {'init_date': time.strftime('%Y-01-01')}
        test_reports.try_report_action(self.cr, self.uid, 'action_hr_attendance_error', wiz_data=data_dict, context=ctx, our_module='hr_attendance')
