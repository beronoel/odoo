# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from openerp.osv import osv
from openerp.tools.misc import formatLang
from openerp.tools.translate import _
from openerp.report import report_sxw
from openerp.exceptions import UserError


class report_expense(report_sxw.rml_parse):

    def set_context(self, objects, data, ids, report_type=None):
        res = super(report_expense, self).set_context(objects, data, ids, report_type=report_type)
        expenses_info = {}
        expenses = self.pool.get('hr.expense').search(self.cr, self.uid, [('id', 'in', ids), ('state', 'in', ('approve', 'submit'))], order="employee_id, currency_id, state, date")
        if not expenses:
            raise UserError(_('Please select one or several expense(s) that are approved or submitted!'))
        for expense in self.pool.get('hr.expense').browse(self.cr, self.uid, expenses):
            key = expense.employee_id.name + '-' + expense.currency_id.name + '-' + expense.state
            if expenses_info.get(key):
                expenses_info[key]['lines'] += expense
                expenses_info[key]['total_amount'] += expense.total_amount
            else:
                expenses_info[key] = {
                                        'employee_name': expense.employee_id.name, 
                                        'total_amount': expense.total_amount, 
                                        'lines': expense,
                                        'currency': expense.currency_id,
                                        'validator_name': expense.employee_id.parent_id.name,
                                        'notes': [],
                                        'notes_index': {},
                                        'state': expense.state,
                                    }
            if expense.description:
                index = len(expenses_info[key]['notes']) + 1
                expenses_info[key]['notes'].append({'description': expense.description, 'index':index})
                expenses_info[key]['notes_index'][expense.id] = index

        self.localcontext.update({
            'expenses': lambda : [v for k,v in sorted(expenses_info.items())],
            })
        return res


class report_hr_expense(osv.AbstractModel):
    _name = 'report.hr_expense.report_expense'
    _inherit = 'report.abstract_report'
    _template = 'hr_expense.report_expense'
    _wrapped_report_class = report_expense
