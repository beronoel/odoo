#-*- coding:utf-8 -*-

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, models


class payslip_report(models.AbstractModel):
    _name = 'report.hr_payroll.report_payslip'
    _inherit = 'report.abstract_report'

    def get_payslip_lines(self, obj):
        payslip_line = self.env['hr.payslip.line']
        res = []
        ids = []
        for id in range(len(obj)):
            if obj[id].appears_on_payslip is True:
                ids.append(obj[id].id)
        if ids:
            res = payslip_line.browse(ids)
        return res

    @api.multi
    def render_html(self, data=None):
        report_payroll = self.env['report']
        report = report_payroll._get_report_from_name('hr_payroll.report_payslip')
        records = self.env['hr.payslip'].browse(self.ids)
        docargs = {
            'doc_ids': self.ids,
            'doc_model': report.model,
            'docs': records,
            'data': data,
            'get_payslip_lines': self.get_payslip_lines,
        }
        return report_payroll.render('hr_payroll.report_payslip', docargs)
