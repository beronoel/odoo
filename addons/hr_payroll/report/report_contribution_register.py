#-*- coding:utf-8 -*-

# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime
from dateutil import relativedelta

from openerp import api, models


class ContributionRegisterReport(models.AbstractModel):
    _name = 'report.hr_payroll.report_contributionregister'
    _inherit = 'report.abstract_report'

    def sum_total(self):
        return self.regi_total

    def _get_payslip_lines(self, obj):
        self.regi_total = 0.0
        self.env.cr.execute("SELECT pl.id from hr_payslip_line as pl "
                        "LEFT JOIN hr_payslip AS hp on (pl.slip_id = hp.id) "
                        "WHERE (hp.date_from >= %s) AND (hp.date_to <= %s) "
                        "AND pl.register_id = %s "
                        "AND hp.state = 'done' "
                        "ORDER BY pl.slip_id, pl.sequence",
                        (self.date_from, self.date_to, obj.id))
        payslip_lines = [x[0] for x in self.env.cr.fetchall()]
        lines = self.env['hr.payslip.line'].browse(payslip_lines)
        for line in lines:
            self.regi_total += line.total
        return lines

    @api.multi
    def render_html(self, data=None):
        self.ensure_one()
        report_payroll = self.env['report']
        self.date_from = data['form'].get('date_from', time.strftime('%Y-%m-%d'))
        self.date_to = data['form'].get('date_to', str(datetime.now() + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10])
        report = report_payroll._get_report_from_name('hr_payroll.report_contributionregister')
        records = self.env['hr.contribution.register'].browse(self.env.context.get('active_ids'))
        docargs = {
            'doc_ids': self.ids,
            'doc_model': report.model,
            'docs': records,
            'data': data,
            'get_payslip_lines': self._get_payslip_lines,
            'sum_total': self.sum_total
        }
        return report_payroll.render('hr_payroll.report_contributionregister', docargs)
