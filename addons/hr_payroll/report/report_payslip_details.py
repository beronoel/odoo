#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, models


class payslip_details_report(models.AbstractModel):
    _name = 'report.hr_payroll.report_payslipdetails'
    _inherit = 'report.abstract_report'

    def get_details_by_rule_category(self, obj):
        payslip_line = self.env['hr.payslip.line']
        rule_cate_obj = self.env['hr.salary.rule.category']

        def get_recursive_parent(rule_categories):
            if not rule_categories:
                return []
            if rule_categories[0].parent_id:
                rule_categories.insert(0, rule_categories[0].parent_id)
                get_recursive_parent(rule_categories)
            return rule_categories

        res = []
        result = {}
        ids = []

        for id in range(len(obj)):
            ids.append(obj[id].id)
        if ids:
            self.env.cr.execute('''SELECT pl.id, pl.category_id FROM hr_payslip_line as pl \
                LEFT JOIN hr_salary_rule_category AS rc on (pl.category_id = rc.id) \
                WHERE pl.id in %s \
                GROUP BY rc.parent_id, pl.sequence, pl.id, pl.category_id \
                ORDER BY pl.sequence, rc.parent_id''', (tuple(obj.ids),))
            for x in self.env.cr.fetchall():
                result.setdefault(x[1], [])
                result[x[1]].append(x[0])
            for key, value in result.iteritems():
                rule_categories = rule_cate_obj.browse([key])
                parents = get_recursive_parent(rule_categories)
                category_total = 0
                for line in payslip_line.browse(value):
                    category_total += line.total
                level = 0
                for parent in parents:
                    res.append({
                        'rule_category': parent.name,
                        'name': parent.name,
                        'code': parent.code,
                        'level': level,
                        'total': category_total,
                    })
                    level += 1
                for line in payslip_line.browse(value):
                    res.append({
                        'rule_category': line.name,
                        'name': line.name,
                        'code': line.code,
                        'total': line.total,
                        'level': level
                    })
        return res

    def get_lines_by_contribution_register(self, obj):
        payslip_line = self.env['hr.payslip.line']
        result = {}
        res = []

        for id in range(len(obj)):
            if obj[id].register_id:
                result.setdefault(obj[id].register_id.name, [])
                result[obj[id].register_id.name].append(obj[id].id)
        for key, value in result.iteritems():
            register_total = 0
            for line in payslip_line.browse(value):
                register_total += line.total
            res.append({
                'register_name': key,
                'total': register_total,
            })
            for line in payslip_line.browse(value):
                res.append({
                    'name': line.name,
                    'code': line.code,
                    'quantity': line.quantity,
                    'amount': line.amount,
                    'total': line.total,
                })
        return res

    @api.multi
    def render_html(self, data=None):
        report_payroll = self.env['report']
        report = report_payroll._get_report_from_name('hr_payroll.report_payslipdetails')
        records = self.env['hr.payslip'].browse(self.ids)
        docargs = {
            'doc_ids': self.ids,
            'doc_model': report.model,
            'docs': records,
            'data': data,
            'get_details_by_rule_category': self.get_details_by_rule_category,
            'get_lines_by_contribution_register': self.get_lines_by_contribution_register,
        }
        return report_payroll.render('hr_payroll.report_payslipdetails', docargs)
