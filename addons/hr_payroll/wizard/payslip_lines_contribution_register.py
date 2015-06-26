# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime
from dateutil import relativedelta
from openerp import api,fields, models


class payslip_lines_contribution_register(models.TransientModel):
    _name = 'payslip.lines.contribution.register'
    _description = 'PaySlip Lines by Contribution Registers'

    date_from = fields.Date(
        string='Date From', required=True, default=lambda *a: time.strftime('%Y-%m-01'))
    date_to = fields.Date(string='Date To', required=True, default=lambda *a: str(
        datetime.now() + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10])

    @api.multi
    def print_report(self):
        datas = {
            'ids': self.env.context.get('active_ids', []),
            'model': 'hr.contribution.register',
            'form': self.read()[0]
        }
        print ">>>>>>>>>>>", self
        records = self.env['hr.payslip'].browse(self._ids)
        return self.env['report'].get_action(
            records, 'hr_payroll.report_contributionregister', data=datas)
