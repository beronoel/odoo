# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from datetime import datetime

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


class HrEmployee(models.Model):
    '''
    Employee
    '''

    _inherit = 'hr.employee'
    _description = 'Employee'

    @api.multi
    def _calculate_total_wage(self):
        if not self:
            return {}
        res = {}
        current_date = datetime.now().strftime('%Y-%m-%d')
        for employee in self:
            if not employee.contract_ids:
                res[employee.id] = {'basic': 0.0}
                continue
            self.env.cr.execute('SELECT SUM(wage) '
                                'FROM hr_contract '
                                'WHERE employee_id = %s '
                                'AND date_start <= %s '
                                'AND (date_end > %s OR date_end is NULL)',
                                (employee.id, current_date, current_date))
            result = dict(self.env.cr.dictfetchone())
            res[employee.id] = {'basic': result['sum']}
        return res

    @api.one
    def _payslip_count(self):
        self.payslip_count = self.env['hr.payslip'].search_count([('employee_id', '=', self.id)])

    slip_ids = fields.One2many(
        'hr.payslip', 'employee_id', string='Payslips', required=False, readonly=True)
    total_wage = fields.Float(
        compute='_calculate_total_wage', string='Total Basic Salary', digits_compute=dp.get_precision('Payroll'), help="Sum of all current contract's wage of employee.")
    payslip_count = fields.Integer(
        compute='_payslip_count', type='integer', string='Payslips')
