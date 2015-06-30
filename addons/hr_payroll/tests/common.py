# -*- coding: utf-8 -*-

import time
from datetime import datetime, timedelta

from openerp.tests import common


class TestHrPayrollCommon(common.TransactionCase):

    def setUp(self):
        super(TestHrPayrollCommon, self).setUp()

        self.HrPayslip = self.env['hr.payslip']
        self.HrPayslipInput = self.env['hr.payslip.input']
        self.HrPayslipEmployees = self.env['hr.payslip.employees']
        self.HrContributionRegister = self.env['hr.contribution.register']
        self.HrEmployee = self.env['hr.employee']
        self.HrPayrollStructure = self.env['hr.payroll.structure']
        self.HrContract = self.env['hr.contract']
        self.HrPayslipRun = self.env['hr.payslip.run']
        self.PayslipLinesContributionRegister = self.env['payslip.lines.contribution.register']
        self.menu_dept_tree = self.env.ref('hr_payroll.menu_department_tree')
        self.country_id = self.env.ref('base.be')
        self.main_company_id = self.env.ref('base.main_company')
        self.rd_department_id = self.env.ref('hr.dep_rd')
        self.rule_id_1 = self.env.ref('hr_payroll.hr_salary_rule_houserentallowance1')
        self.rule_id_2 = self.env.ref('hr_payroll.hr_salary_rule_convanceallowance1')
        self.rule_id_3 = self.env.ref('hr_payroll.hr_salary_rule_professionaltax1')
        self.rule_id_4 = self.env.ref('hr_payroll.hr_salary_rule_providentfund1')
        self.rule_id_5 = self.env.ref('hr_payroll.hr_salary_rule_meal_voucher')
        self.rule_id_6 = self.env.ref('hr_payroll.hr_salary_rule_sales_commission')
        self.emp_type_id = self.env.ref('hr_contract.hr_contract_type_emp')
        self.working_hours_id = self.env.ref('resource.timesheet_group1')

        # create a new employee "Richard"
        self.employee_richard = self.HrEmployee.create({
            'birthday': '1984-05-01',
            'country_id': self.country_id.id,
            'department_id': self.rd_department_id.id,
            'gender': 'male',
            'name': 'Richard'
        })

        # create a salary structure
        self.sd_payroll_structure = self.HrPayrollStructure.create({
            'name': 'Salary Structure for Software Developer',
            'code': 'SD',
            'company_id': self.main_company_id.id,
            'rule_ids': [(6, 0, {self.rule_id_1.id, self.rule_id_2.id, self.rule_id_3.id, self.rule_id_4.id, self.rule_id_5.id, self.rule_id_6.id})]
        })

        # create a contract
        self.hr_contract_richard = self.HrContract.create({
            'date_end': (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d'),
            'date_start': time.strftime('%Y-%m-%d'),
            'name': 'Contract for Richard',
            'wage': 5000.0,
            'type_id': self.emp_type_id.id,
            'employee_id': self.employee_richard.id,
            'struct_id': self.sd_payroll_structure.id,
            'working_hours': self.working_hours_id.id
        })

        # create employee payslip
        self.richard_payslip = self.HrPayslip.create({
            'employee_id': self.employee_richard.id
        })

        #I want to generate a payslip from Payslip run.
        self.payslip_run = self.HrPayslipRun.create({
            'date_end': '2011-09-30',
            'date_start': '2011-09-01',
            'name': 'Payslip for Employee'})

        # generate payslip
        self.payslip_employees = self.HrPayslipEmployees.create({
            'employee_ids': [(6, 0, {self.employee_richard.id})]
        })

        #I open Contribution Register and from there I print the Payslip Lines report.
        self.payslip_lines_contribution_register = self.PayslipLinesContributionRegister.create({
            'date_from': '2011-09-30',
            'date_to': '2011-09-01'})
