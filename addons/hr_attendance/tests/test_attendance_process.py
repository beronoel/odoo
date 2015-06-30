# -*- coding: utf-8 -*-

import time

from openerp.exceptions import ValidationError
from openerp.tests import common


class TestAttendanceProcess(common.TransactionCase):

    def setUp(self):
        super(TestAttendanceProcess, self).setUp()

        self.ResUsers = self.env['res.users']
        self.ResEmployee = self.env['hr.employee']
        self.Attendance = self.env['hr.attendance']
        self.Company = self.env.ref('base.main_company')
        self.hr_employee_niv = self.env.ref('hr.employee_niv')
        self.group_hr_user = self.env.ref('base.group_hr_user')
        # Create a user as 'HR Attendance Officer.'
        self.res_users_attendance_officer = self.ResUsers.create({
            'company_id': self.Company.id,
            'name': 'HR Officer',
            'login': 'ao',
            'password': 'ao',
            'groups_id': [(6, 0, [self.group_hr_user.id])]})
        self.hr_employeeall = self.env.ref('hr.employee_al').with_context({'uid': self.res_users_attendance_officer.id})

    def test_hr_attendance_process(self):
        # Give the access rights of Hr Officer to test attendance process.
        # In order to test attendance process in OpenERP, I entry of signin of employee.

        self.hr_employeeall.attendance_action_change()
        #-------------------------------------
        # I check that employee is "present".
        #-------------------------------------

        self.hr_employeeall.invalidate_cache()
        self.assertEqual(self.hr_employeeall.state, 'present', 'Employee should be in present state.')
        # After few seconds, employee sign's out.
        time.sleep(2)
        self.hr_employeeall.attendance_action_change()

        #-------------------------------------
        # I check that employee is "absent".
        #-------------------------------------
        self.hr_employeeall.invalidate_cache()
        self.assertEqual(self.hr_employeeall.state, 'absent', 'Employee should be in absent state.')

        # In order to check that first attendance must be sign in.
        try:
            self.attendance = self.Attendance.create({
                'employee_id': self.hr_employee_niv.id,
                'name': time.strftime('%Y-%m-%d 09:59:25'),
                'action': 'sign_out'
            })
        except ValidationError:
            pass

        # First of all, employee sign's in.
        self.attendance = self.Attendance.create({
            'employee_id': self.hr_employee_niv.id,
            'name': time.strftime('%Y-%m-%d 09:59:25'),
            'action': 'sign_in'
        })

        # Now employee is going to sign in prior to first sign in.
        try:
            self.attendance = self.Attendance.create({
                'employee_id': self.hr_employee_niv.id,
                'name': time.strftime('%Y-%m-%d 08:59:25'),
                'action': 'sign_in'
            })
        except ValidationError:
            pass

        # After that employee is going to sign in after first sign in.
        try:
            self.attendance = self.Attendance.create({
                'employee_id': self.hr_employee_niv.id,
                'name': time.strftime('%Y-%m-%d 10:59:25'),
                'action': 'sign_in'
            })
        except ValidationError:
            pass

        # After two hours, employee sign's out.
        self.attendance = self.Attendance.create({
            'employee_id': self.hr_employee_niv.id,
            'name': time.strftime('%Y-%m-%d 11:59:25'),
            'action': 'sign_out'
        })

        # Now employee is going to sign out prior to sirst sign out.
        try:
            self.attendance = self.Attendance.create({
                'employee_id': self.hr_employee_niv.id,
                'name': time.strftime('%Y-%m-%d 10:59:25'),
                'action': 'sign_out'
            })
        except ValidationError:
            pass

        # After that employee is going to sign out after first sign out.
        try:
            self.attendance = self.Attendance.create({
                'employee_id': self.hr_employee_niv.id,
                'name': time.strftime('%Y-%m-%d 12:59:25'),
                'action': 'sign_out'
            })
        except ValidationError:
            pass
