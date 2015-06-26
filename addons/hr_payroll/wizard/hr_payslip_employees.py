# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
from openerp.tools.translate import _
from openerp.exceptions import UserError


class hr_payslip_employees(models.TransientModel):

    _name = 'hr.payslip.employees'
    _description = 'Generate payslips for all selected employees'

    employee_ids = fields.Many2many(
        'hr.employee', 'hr_employee_group_rel', 'payslip_id', 'employee_id', string='Employees')

    @api.multi
    def compute_sheet(self):
        HrPayslip = payslips = self.env['hr.payslip']
        HrPayslipRun = payslip_run = self.env['hr.payslip.run']
        if self.env.context and self.env.context.get('active_id'):
            payslip_run = HrPayslipRun.browse(self.env.context['active_id'])
        from_date = payslip_run.date_start
        to_date = payslip_run.date_end
        credit_note = payslip_run.credit_note
        if not self.employee_ids:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))
        for emp in self.employee_ids:
            slip_data = HrPayslip.onchange_employee_id(from_date, to_date, emp.id, contract_id=False)

            res = {
                'employee_id': emp.id,
                'name': slip_data['value'].get('name'),
                'struct_id': slip_data['value'].get('struct_id'),
                'contract_id': slip_data['value'].get('contract_id'),
                'payslip_run_id': self.env.context.get('active_id'),
                'input_line_ids': [(0, 0, x) for x in slip_data['value'].get('input_line_ids')],
                'worked_days_line_ids': [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids')],
                'date_from': from_date,
                'date_to': to_date,
                'credit_note': credit_note,
            }
            payslips |= HrPayslip.create(res)
        payslips.compute_sheet()
        return {'type': 'ir.actions.act_window_close'}
