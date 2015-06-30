# -*- coding: utf-8 -*-

import os

from openerp import report as odoo_report
from openerp.tools import test_reports
from openerp import tools
from openerp.addons.hr_payroll.tests.common import TestHrPayrollCommon


class TestHrPayrollFlow(TestHrPayrollCommon):

    def test_00_hr_payslip(self):
        """ checking the process of payslip. """

        # I assign the amount to Input data.
        payslip = self.HrPayslipInput.search([('payslip_id', '=', self.payslip_employees.id)])
        payslip.write({'amount': 5.0})

        # I verify the payslip is in done state.
        self.assertEqual(self.richard_payslip.state, 'draft', 'State not changed!')

        # I click on "Compute Sheet" button.
        context = {"lang": "en_US", "tz": False, "active_model": 'ir.ui.menu', "department_id": False, "active_ids": [self.menu_dept_tree.id], "section_id": False, "active_id": self.menu_dept_tree.id}
        self.richard_payslip.with_context(context).compute_sheet()

        # Confirm Payslip
        self.richard_payslip.signal_workflow('hr_verify_sheet')

        # I verify that the payslip is in done state.
        self.assertEqual(self.richard_payslip.state, 'done', 'State not changed!')

        #I want to check refund payslip so I click on refund button.
        change_employee = self.richard_payslip.onchange_employee_id_wrapper()
        self.richard_payslip.refund_sheet()

        #I check on new payslip Credit Note is checked or not.
        payslip_ids = self.richard_payslip.search([('name', 'like', 'Refund: ' + self.richard_payslip.name), ('credit_note', '=', True)])
        self.assertTrue(payslip_ids, "Payslip not refunded!")

        #I generate the payslip by clicking on Generat button wizard.
        context = {'active_id': self.payslip_run.id}
        self.payslip_employees.with_context(context).compute_sheet()

        # I print the payslip report
        data, format = odoo_report.render_report(self.env.cr, self.env.uid, self.richard_payslip.id, 'hr_payroll.report_payslip', {}, {})
        if tools.config['test_report_directory']:
            file(os.path.join(tools.config['test_report_directory'], 'hr_payroll-payslip.'+format), 'wb+').write(data)

        #I print the payslip details report
        data, format = odoo_report.render_report(self.env.cr, self.env.uid, self.richard_payslip.id, 'hr_payroll.report_payslipdetails', {}, {})
        if tools.config['test_report_directory']:
            file(os.path.join(tools.config['test_report_directory'], 'hr_payroll-payslipdetails.'+format), 'wb+').write(data)

        #I print the contribution register report
        ctx={'active_model': 'hr.contribution.register', 'active_ids': [self.env.ref('hr_payroll.hr_houserent_register').id]}
        test_reports.try_report_action(self.env.cr, self.env.uid, 'action_payslip_lines_contribution_register', context=ctx, our_module='hr_payroll')
