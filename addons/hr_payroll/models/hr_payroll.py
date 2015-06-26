#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime, timedelta
from dateutil import relativedelta

from openerp import api, fields, models, tools
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

from openerp.tools.safe_eval import safe_eval as eval
from openerp.exceptions import UserError, ValidationError


class HrPayrollStructure(models.Model):
    """
    Salary structure used to defined
    - Basic
    - Allowances
    - Deductions
    """

    _name = 'hr.payroll.structure'
    _description = 'Salary Structure'

    name = fields.Char(required=True)
    code = fields.Char(string='Reference', size=64, required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, copy=False, default=lambda self:
        self.env['res.users'].browse().company_id.id)
    note = fields.Text(string='Description')
    parent_id = fields.Many2one('hr.payroll.structure', string='Parent', default='_get_parent')
    children_ids = fields.One2many('hr.payroll.structure', 'parent_id', string='Children', copy=True)
    rule_ids = fields.Many2many('hr.salary.rule', 'hr_structure_salary_rule_rel', 'struct_id', 'rule_id', string='Salary Rules')

    def _get_parent(self):
        return self.env['ir.model.data'].search([('model', '=', 'hr.payroll.structure'), ('name', '=', 'structure_base')], limit=1).res_id

    @api.constrains('parent_id')
    def check_recursion(self):
        if not self._check_recursion():
            raise ValidationError(
                _('Error ! You cannot create a recursive Salary Structure.'))

    def copy(self, default=None):
        default = dict(default or {},
                       code=_("%s (copy)") % (self.code))
        return super(HrPayrollStructure, self).copy(default)

    @api.multi
    def get_all_rules(self, structure_ids):
        """
        @param structure_ids: list of structure
        @return: returns a list of tuple (id, sequence) of rules that are maybe to apply
        """

        all_rules = []
        for struct in self.browse(structure_ids):
            all_rules += self.env['hr.salary.rule']._recursive_search_of_rules(struct.rule_ids)
        return all_rules

    @api.multi
    def _get_parent_structure(self):
        parent = []
        for struct in self:
            if struct.parent_id:
                parent.append(struct.parent_id.id)
        if parent:
            parent = self.browse(parent)._get_parent_structure()
        return parent + self.ids


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """

    _inherit = 'hr.contract'
    _description = 'Employee Contract'

    struct_id = fields.Many2one('hr.payroll.structure', string='Salary Structure')
    schedule_pay = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi-annually', 'Semi-annually'),
        ('annually', 'Annually'),
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-weekly'),
        ('bi-monthly', 'Bi-monthly'),
    ], string='Scheduled Pay', select=True, default='monthly')

    @api.multi
    def get_all_structures(self, contract_ids):
        """
        @param contract_ids: list of contracts
        @return: the structures linked to the given contracts, ordered by hierachy (parent=False first, then first level children and so on) and without duplicata
        """
        structure_ids = [contract.struct_id.id for contract in self.browse(
            contract_ids) if contract.struct_id]
        if not structure_ids:
            return []
        return self.env['hr.payroll.structure'].browse(structure_ids)._get_parent_structure()


class HrContribRegister(models.Model):
    '''
    Contribution Register
    '''

    _name = 'hr.contribution.register'
    _description = 'Contribution Register'

    company_id = fields.Many2one('res.company', string='Company', default=lambda self:
        self.env.user.company_id.id)
    partner_id = fields.Many2one('res.partner', string='Partner')
    name = fields.Char(required=True, readonly=False)
    register_line_ids = fields.One2many('hr.payslip.line', 'register_id', string='Register Line', readonly=True)
    note = fields.Text(string='Description')


class HrSalaryRuleCategory(models.Model):
    """
    HR Salary Rule Category
    """

    _name = 'hr.salary.rule.category'
    _description = 'Salary Rule Category'

    name = fields.Char(required=True, readonly=False)
    code = fields.Char(size=64, required=True, readonly=False)
    parent_id = fields.Many2one('hr.salary.rule.category', string='Parent', help="Linking a salary category to its parent is used only for the reporting purpose.")
    children_ids = fields.One2many('hr.salary.rule.category', 'parent_id', string='Children')
    note = fields.Text(string='Description')
    company_id = fields.Many2one('res.company', string='Company', required=False, default=lambda self:
                self.env.user.company_id.id)


class One2many_mod2(fields.One2many):

    def get(self, obj, ids, user=None, offset=0, values=None):
        if not values:
            values = {}
        res = {}
        for id in self:
            res[id] = []
        ids2 = obj.pool[self._obj].search(user, [(
            self._fields_id, 'in', self), ('appears_on_payslip', '=', True)], limit=self._limit)
        for r in obj.pool[self._obj].read(user, ids2, [self._fields_id], load='_classic_write'):
            key = r[self._fields_id]
            if isinstance(key, tuple):
                # Read return a tuple in the case where the field is a many2one
                # but we want to get the id of this field.
                key = key[0]

            res[key].append(r['id'])
        return res


class HrPayslipRun(models.Model):

    _name = 'hr.payslip.run'
    _description = 'Payslip Batches'

    name = fields.Char(required=True, readonly=True, states={'draft': [('readonly', False)]})
    slip_ids = fields.One2many('hr.payslip', 'payslip_run_id', string='Payslips', required=False, readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection([
        ('draft', 'Draft'),
        ('close', 'Close'),
    ], string='Status', select=True, readonly=True, copy=False, default='draft')
    date_start = fields.Date(string='Date From', required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda *a: time.strftime('%Y-%m-01'))
    date_end = fields.Date(string='Date To', required=True, readonly=True, states={'draft': [('readonly', False)]}, default=lambda *a: str(datetime.now() + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10])
    credit_note = fields.Boolean(string='Credit Note', readonly=True, states={'draft': [('readonly', False)]}, help="If its checked, indicates that all payslips generated from here are refund payslips.")

    @api.multi
    def draft_payslip_run(self):
        return self.write({'state': 'draft'})

    @api.multi
    def close_payslip_run(self):
        return self.write({'state': 'close'})


class HrPayslip(models.Model):
    '''
    Pay Slip
    '''

    _name = 'hr.payslip'
    _description = 'Pay Slip'

    @api.multi
    def _get_lines_salary_rule_category(self):
        result = {}
        for payslip in self:
            result.setdefault(payslip.id, [])
        self.env.cr.execute('''SELECT pl.slip_id, pl.id FROM hr_payslip_line AS pl \
                    LEFT JOIN hr_salary_rule_category AS sh on (pl.category_id = sh.id) \
                    WHERE pl.slip_id in %s \
                    GROUP BY pl.slip_id, pl.sequence, pl.id ORDER BY pl.sequence''',(tuple(self.ids),))
        res = self.env.cr.fetchall()
        for r in res:
            result[r[0]].append(r[1])
        return result

    @api.one
    def _count_detail_payslip(self):
        for payslip in self:
            self.payslip_count = len(payslip.line_ids)

    struct_id = fields.Many2one('hr.payroll.structure', string='Structure', readonly=True, states={'draft': [('readonly', False)]}, help='Defines the rules that have to be applied to this payslip, accordingly to the contract chosen. If you let empty the field contract, this field isn\'t mandatory anymore and thus the rules applied will be all the rules set on the structure of all contracts of the employee valid for the chosen period')
    name = fields.Char(string='Payslip Name', required=False, readonly=True, states={'draft': [('readonly', False)]})
    number = fields.Char(string='Reference', required=False, readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, readonly=True, states={'draft': [('readonly', False)]})
    date_from = fields.Date(string='Date From', readonly=True, default=lambda *a: time.strftime('%Y-%m-01'), states={'draft': [('readonly', False)]}, required=True)
    date_to = fields.Date(string='Date To', readonly=True, default=lambda *a: str(datetime.now() + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10], states={'draft': [('readonly', False)]}, required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ], string='Status', select=True, readonly=True, copy=False, default='draft',
        help='* When the payslip is created the status is \'Draft\'.\
            \n* If the payslip is under verification, the status is \'Waiting\'. \
            \n* If the payslip is confirmed then status is set to \'Done\'.\
            \n* When user cancel payslip the status is \'Rejected\'.')
    line_ids = One2many_mod2('hr.payslip.line', 'slip_id', string='Payslip Lines', readonly=True, states={
                             'draft': [('readonly', False)]})
    company_id = fields.Many2one('res.company', string='Company', required=False, default=lambda self: self.env['res.users'].browse().company_id.id, readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    worked_days_line_ids = fields.One2many('hr.payslip.worked_days', 'payslip_id', string='Payslip Worked Days', required=False, readonly=True, states={'draft': [('readonly', False)]})
    input_line_ids = fields.One2many('hr.payslip.input', 'payslip_id', string='Payslip Inputs', required=False, readonly=True, states={'draft': [('readonly', False)]})
    paid = fields.Boolean(string='Made Payment Order ? ', required=False, readonly=True, states={'draft': [('readonly', False)]}, copy=False)
    note = fields.Text(
        string='Internal Note', readonly=True, states={'draft': [('readonly', False)]})
    contract_id = fields.Many2one('hr.contract', string='Contract', required=False, readonly=True, states={'draft': [('readonly', False)]})
    details_by_salary_rule_category = fields.One2many('hr.payslip.line', compute='_get_lines_salary_rule_category', string='Details by Salary Rule Category')
    credit_note = fields.Boolean(string='Credit Note', help="Indicates this payslip has a refund of another", readonly=True, default=False, states={'draft': [('readonly', False)]})
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Payslip Batches', readonly=True, states={
        'draft': [('readonly', False)]}, copy=False)
    payslip_count = fields.Integer(
        compute='_count_detail_payslip', string='Payslip Computation Details')

    @api.multi
    def _check_dates(self):
        for payslip in self:
            if payslip.date_from > payslip.date_to:
                return False
        return True

    @api.constrains('date_from', 'date_to')
    def check_dates(self):
        if not self._check_dates():
            raise ValidationError(
                _("Payslip 'Date From create must be before 'Date To'"))

    @api.multi
    def cancel_sheet(self):
        return self.write({'state': 'cancel'})

    @api.multi
    def process_sheet(self):
        return self.write({'paid': True, 'state': 'done'})

    @api.multi
    def hr_verify_sheet(self):
        self.compute_sheet()
        return self.write({'state': 'verify'})

    @api.multi
    def refund_sheet(self):
        for payslip in self:
            refunded_payslip = payslip.copy({
                'credit_note': True, 'name': _('Refund: ')+payslip.name})
            refunded_payslip.compute_sheet()
            refunded_payslip.signal_workflow('hr_verify_sheet')
            refunded_payslip.signal_workflow('process_sheet')
        form_res = self.env.ref('hr_payroll.view_hr_payslip_form').id
        tree_res = self.env.ref('hr_payroll.view_hr_payslip_tree').id
        return {
            'name': _("Refund Payslip"),
            'view_mode': 'tree, form',
            'view_id': False,
            'view_type': 'form',
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'domain': "[('id', 'in', %s)]" % [refunded_payslip.id],
            'views': [(tree_res, 'tree'), (form_res, 'form')],
            'context': {}
        }

    def check_done(self):
        return True

    @api.multi
    def unlink(self):
        for payslip in self:
            if payslip.state not in ['draft', 'cancel']:
                raise UserError(_('You cannot delete a payslip which is not draft or cancelled!'))
        return super(HrPayslip, self).unlink()


    #TODO move this function into hr_contract module, on hr.employee object
    def get_contract(self, employee, date_from, date_to):
        """
        @param employee: browse record of employee
        @param date_from: date field
        @param date_to: date field
        @return: returns the ids of all the contracts for the given employee that need to be considered for the given dates
        """
        HrContract = self.env['hr.contract']
        clause = []
        #a contract is valid if it ends between the given dates
        clause_1 = [
            '&', ('date_end', '<=', date_to), ('date_end', '>=', date_from)]
        #OR if it starts between the given dates
        clause_2 = [
            '&', ('date_start', '<=', date_to), ('date_start', '>=', date_from)]
        #OR if it starts before the date_from and finish after the date_end (or never finish)
        clause_3 = [
            '&', ('date_start', '<=', date_from), '|', ('date_end', '=', False), ('date_end', '>=', date_to)]
        clause_final = [
        ('employee_id', '=', employee.id), '|', '|'] + clause_1 + clause_2 + clause_3
        return HrContract.search(clause_final).ids

    @api.multi
    def compute_sheet(self):
        HrPayslipLine = self.env['hr.payslip.line']
        IrSequence = self.env['ir.sequence']
        for payslip in self:
            number = payslip.number or IrSequence.next_by_code('salary.slip')
            #delete old payslip lines
            old_sliplines = HrPayslipLine.search([('slip_id', '=', payslip.id)])
#            old_slipline_ids
            if old_sliplines:
                old_sliplines.unlink()
            if payslip.contract_id:
                #set the list of contract for which the rules have to be applied
                contract_ids = [payslip.contract_id.id]
            else:
                #if we don't give the contract, then the rules to apply should be for all current contracts of the employee
                contract_ids = self.get_contract(payslip.employee_id, payslip.date_from, payslip.date_to)
            lines = [(0, 0, line) for line in payslip.get_payslip_lines(contract_ids)]
            payslip.write({'line_ids': lines, 'number': number})
        return True

    @api.multi
    def get_worked_day_lines(self, contract_ids, date_from, date_to):
        """
        @param contract_ids: list of contract id
        @return: returns a list of dict containing the input that should be applied for the given contract between date_from and date_to
        """
        def was_on_leave(employee_id, datetime_day):
            res = False
            day = datetime_day.strftime("%Y-%m-%d")
            holiday = self.env['hr.holidays'].search([('state', '=', 'validate'),(
                'employee_id', '=', employee_id), ('type', '=', 'remove'), ('date_from', '<=', day), ('date_to', '>=', day)], limit=1)
            return holiday.holiday_status_id.name

        res = []
        for contract in self.env['hr.contract'].browse(contract_ids):
            if not contract.working_hours:
                #fill only if the contract as a working schedule linked
                continue
            attendances = {
                'name': _("Normal Working Days paid at 100%"),
                'sequence': 1,
                'code': 'WORK100',
                'number_of_days': 0.0,
                'number_of_hours': 0.0,
                'contract_id': contract.id,
            }
            leaves = {}
            day_from = datetime.strptime(date_from,"%Y-%m-%d")
            day_to = datetime.strptime(date_to,"%Y-%m-%d")
            nb_of_days = (day_to - day_from).days + 1
            for day in range(0, nb_of_days):
                working_hours_on_day = self.env['resource.calendar'].working_hours_on_day(
                    contract.working_hours, day_from + timedelta(days=day))
                if working_hours_on_day:
                    #the employee had to work
                    leave_type = was_on_leave(
                        contract.employee_id.id, day_from + timedelta(days=day))
                    if leave_type:
                        #if he was on leave, fill the leaves dict
                        if leave_type in leaves:
                            leaves[leave_type]['number_of_days'] += 1.0
                            leaves[leave_type]['number_of_hours'] += working_hours_on_day
                        else:
                            leaves[leave_type] = {
                                'name': leave_type,
                                'sequence': 5,
                                'code': leave_type,
                                'number_of_days': 1.0,
                                'number_of_hours': working_hours_on_day,
                                'contract_id': contract.id,
                            }
                    else:
                        #add the input vals to tmp (increment if existing)
                        attendances['number_of_days'] += 1.0
                        attendances['number_of_hours'] += working_hours_on_day
            leaves = [value for key, value in leaves.items()]
            res += [attendances] + leaves
        return res

    def get_inputs(self, contract_ids):
        res = []
        HrContract = self.env['hr.contract']
        HrSalaryRule = self.env['hr.salary.rule']

        structure_ids = HrContract.browse(contract_ids).get_all_structures(contract_ids)
        rule_ids = self.env['hr.payroll.structure'].get_all_rules(structure_ids)
        sorted_rule_ids = [
            id for id, sequence in sorted(rule_ids, key=lambda x:x[1])]

        for contract in HrContract.browse(contract_ids):
            for rule in HrSalaryRule.browse(sorted_rule_ids):
                if rule.input_ids:
                    for input in rule.input_ids:
                        inputs = {
                            'name': input.name,
                            'code': input.code,
                            'contract_id': contract.id,
                        }
                        res += [inputs]
        return res

    @api.multi
    def get_payslip_lines(self, contract_ids):
        self.ensure_one()

        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(
                    localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = category.code in localdict[
                'categories'].dict and localdict['categories'].dict[category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, pool, employee_id, dict):
                self.pool = pool
                self.employee_id = employee_id
                self.dict = dict

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                result = 0.0
                self.env.cr.execute("SELECT sum(amount) as sum\
                            FROM hr_payslip as hp, hr_payslip_input as pi \
                            WHERE hp.employee_id = %s AND hp.state = 'done' \
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s",
                           (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()[0]
                return res or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                result = 0.0
                self.env.cr.execute("SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours\
                            FROM hr_payslip as hp, hr_payslip_worked_days as pi \
                            WHERE hp.employee_id = %s AND hp.state = 'done'\
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s",
                           (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                self.env.cr.execute("SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
                            FROM hr_payslip as hp, hr_payslip_line as pl \
                            WHERE hp.employee_id = %s AND hp.state = 'done' \
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
                            (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

        #we keep a dict with the result because a value can be overwritten by another rule with the same code
        result_dict = {}
        rules = {}
        categories_dict = {}
        blacklist = []
        HrSalaryRule = self.env['hr.salary.rule']
        payslip = self
        worked_days = {}
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days[worked_days_line.code] = worked_days_line
        inputs = {}
        for input_line in payslip.input_line_ids:
            inputs[input_line.code] = input_line

        categories_obj = BrowsableObject(
            self.pool, payslip.employee_id.id, categories_dict)
        input_obj = InputLine(
            self.pool, payslip.employee_id.id, inputs)
        worked_days_obj = WorkedDays(
            self.pool, payslip.employee_id.id, worked_days)
        payslip_obj = Payslips(
            self.pool, payslip.employee_id.id, payslip)
        rules_obj = BrowsableObject(
            self.pool, payslip.employee_id.id, rules)

        baselocaldict = {'categories': categories_obj, 'rules': rules_obj,
            'payslip': payslip_obj, 'worked_days': worked_days_obj, 'inputs': input_obj}
        #get the ids of the structures on the contracts and their parent id as well
        structure_ids = self.env['hr.contract'].get_all_structures(contract_ids)
        #get the rules of the structure and thier children
        rule_ids = self.env['hr.payroll.structure'].get_all_rules(structure_ids)
        #run the rules by sequence
        sorted_rule_ids = [
            id for id, sequence in sorted(rule_ids, key=lambda x:x[1])]

        for contract in self.env['hr.contract'].browse(contract_ids):
            employee = contract.employee_id
            localdict = dict(
                baselocaldict, employee=employee, contract=contract)
            for rule in HrSalaryRule.browse(sorted_rule_ids):
                key = rule.code + '-' + str(contract.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                #check if the rule can be applied
                if HrSalaryRule.satisfy_condition(rule.id, localdict) and rule.id not in blacklist:
                    #compute the amount of the rule
                    amount, qty, rate = HrSalaryRule.compute_rule(
                        rule.id, localdict)
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[
                        rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = amount * qty * rate / 100.0
                    localdict[rule.code] = tot_rule
                    rules[rule.code] = rule
                    #sum the amount for its salary category
                    localdict = _sum_salary_rule_category(
                        localdict, rule.category_id, tot_rule - previous_amount)
                    #create/overwrite the rule in the temporary results
                    result_dict[key] = {
                        'salary_rule_id': rule.id,
                        'contract_id': contract.id,
                        'name': rule.name,
                        'code': rule.code,
                        'category_id': rule.category_id.id,
                        'sequence': rule.sequence,
                        'appears_on_payslip': rule.appears_on_payslip,
                        'condition_select': rule.condition_select,
                        'condition_python': rule.condition_python,
                        'condition_range': rule.condition_range,
                        'condition_range_min': rule.condition_range_min,
                        'condition_range_max': rule.condition_range_max,
                        'amount_select': rule.amount_select,
                        'amount_fix': rule.amount_fix,
                        'amount_python_compute': rule.amount_python_compute,
                        'amount_percentage': rule.amount_percentage,
                        'amount_percentage_base': rule.amount_percentage_base,
                        'register_id': rule.register_id.id,
                        'amount': amount,
                        'employee_id': contract.employee_id.id,
                        'quantity': qty,
                        'rate': rate,
                    }
                else:
                    #blacklist this rule and its children
                    blacklist += [id for id, seq in self.env[
                        'hr.salary.rule']._recursive_search_of_rules([rule])]

        result = [value for code, value in result_dict.items()]
        return result

    @api.multi
    @api.onchange('employee_id', 'date_from')
    def onchange_employee_id_wrapper(self):
        self.ensure_one()
        values = self.onchange_employee_id(self.date_from, self.date_to, self.employee_id.id, self.contract_id.id)['value']
        for fname, value in values.iteritems():
            setattr(self, fname, value)

    @api.multi
    def onchange_employee_id(self, date_from, date_to, employee_id=False, contract_id=False):
        HrEmployee = self.env['hr.employee']
        HrContract = self.env['hr.contract']
        HrPayslipWorkedDays = self.env['hr.payslip.worked_days']
        HrPayslipInput = self.env['hr.payslip.input']

        #delete old worked days lines
        old_worked_days_ids = self.ids and HrPayslipWorkedDays.search(
            [('payslip_id', '=', self.ids[0])])
        if old_worked_days_ids:
            old_worked_days_ids.unlink()

        #delete old input lines
        old_input_ids = self.ids and HrPayslipInput.search(
            [('payslip_id', '=', self.ids[0])])
        if old_input_ids:
            old_input_ids.unlink()

        #defaults
        res = {'value': {
            'line_ids': [],
            'input_line_ids': [],
            'worked_days_line_ids': [],
            #'details_by_salary_head':[], TODO put me back
            'name': '',
            'contract_id': False,
            'struct_id': False,
        }
        }
        if (not employee_id) or (not date_from) or (not date_to):
            return res
        ttyme = datetime.fromtimestamp(
            time.mktime(time.strptime(date_from, "%Y-%m-%d")))
        employee_id = HrEmployee.browse(employee_id)
        res['value'].update({
                    'name': _('Salary Slip of %s for %s') % (employee_id.name, tools.ustr(ttyme.strftime('%B-%Y'))),
                    'company_id': employee_id.company_id.id
        })

        if not self.env.context.get('contract', False):
            #fill with the first contract of the employee
            contract_ids = self.get_contract(employee_id, date_from, date_to)
        else:
            if contract_id:
                #set the list of contract for which the input have to be filled
                contract_ids = [contract_id]
            else:
                #if we don't give the contract, then the input to fill should be for all current contracts of the employee
                contract_ids = self.get_contract(employee_id, date_from, date_to)

        if not contract_ids:
            return res
        contract_record = self.env['hr.contract'].browse(contract_ids[0])
        res['value'].update({
            'contract_id': contract_record and contract_record.id or False
        })
        struct_record = contract_record and contract_record.struct_id or False
        if not struct_record:
            return res
        res['value'].update({
            'struct_id': struct_record.id,
        })
        #computation of the salary input
        worked_days_line_ids = self.get_worked_day_lines(contract_ids, date_from, date_to)
        input_line_ids = self.get_inputs(contract_ids)
        res['value'].update({
            'worked_days_line_ids': worked_days_line_ids,
            'input_line_ids': input_line_ids,
        })
        return res

    @api.multi
    @api.onchange('contract_id')
    def onchange_contract_id_wrapper(self):
        self.ensure_one()
        values = self.onchange_contract_id(self.date_from, self.date_to, self.employee_id.id, self.contract_id.id)['value']
        for fname, value in values.iteritems():
            setattr(self, fname, value)

    @api.multi
    def onchange_contract_id(self, date_from, date_to, employee_id=False, contract_id=False):
#TODO it seems to be the mess in the onchanges, we should have onchange_employee => onchange_contract => doing all the things
        res = {'value': {
            'line_ids': [],
            'name': '',
        }
        }
        self.env.context = dict(self.env.context or {}, contract=True)
        if not contract_id:
            res['value'].update({'struct_id': False})
        return self.onchange_employee_id(date_from=date_from, date_to=date_to, employee_id=employee_id, contract_id=contract_id)


class HrPayslipWorkedDays(models.Model):
    '''
    Payslip Worked Days
    '''

    _name = 'hr.payslip.worked_days'
    _description = 'Payslip Worked Days'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade', select=True)
    sequence = fields.Integer(string='Sequence', required=True, select=True, default=10)
    code = fields.Char(size=52, required=True, help="The code that can be used in the salary rules")
    number_of_days = fields.Float(string='Number of Days')
    number_of_hours = fields.Float(string='Number of Hours')
    contract_id = fields.Many2one('hr.contract', string='Contract', required=True, help="The contract for which applied this input")

    _order = 'payslip_id, sequence'


class HrPayslipInput(models.Model):
    '''
    Payslip Input
    '''

    _name = 'hr.payslip.input'
    _description = 'Payslip Input'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade', select=True)
    sequence = fields.Integer(required=True, select=True, default=10)
    code = fields.Char(size=52, required=True, help="The code that can be used in the salary rules")
    amount = fields.Float(default=0.0, help="It is used in computation. For e.g. A rule for sales having 1% commission of basic salary for per product can defined in expression like result = inputs.SALEURO.amount * contract.wage*0.01.")
    contract_id = fields.Many2one('hr.contract', string='Contract', required=True, help="The contract for which applied this input")

    _order = 'payslip_id, sequence'


class HrSalaryRule(models.Model):

    _name = 'hr.salary.rule'

    name = fields.Char(required=True, readonly=False)
    code = fields.Char(size=64, required=True, help="The code of salary rules can be used as reference in computation of other rules. In that case, it is case sensitive.")
    sequence = fields.Integer(required=True, help='Use to arrange calculation sequence', default=5, select=True)
    quantity = fields.Char(default=1.0, help="It is used in computation for percentage and fixed amount.For e.g. A rule for Meal Voucher having fixed amount of 1€ per worked day can have its quantity defined in expression like worked_days.WORK100.number_of_days.")
    category_id = fields.Many2one('hr.salary.rule.category', string='Category', required=True)
    active = fields.Boolean(default=True, help="If the active field is set to false, it will allow you to hide the salary rule without removing it.")
    appears_on_payslip = fields.Boolean(default= True, string='Appears on Payslip', help="Used to display the salary rule on payslip.")
    parent_rule_id = fields.Many2one('hr.salary.rule', string='Parent Salary Rule', select=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=False, default=lambda self:
        self.env['res.users'].browse().company_id.id)
    condition_select = fields.Selection([('none', 'Always True'), ('range', 'Range'), (
        'python', 'Python Expression')], "Condition Based on", required=True, default='none')
    condition_range = fields.Char(string='Range Based on', readonly=False, default='contract.wage', help='This will be used to compute the % fields values; in general it is on basic, but you can also use categories code fields in lowercase as a variable names (hra, ma, lta, etc.) and the variable basic.')
    condition_python = fields.Text(string='Python Condition', required=True, readonly=False, help='Applied this rule for calculation if condition is true. You can specify condition like basic > 1000.')
    condition_range_min = fields.Float(string='Minimum Range', required=False, help="The minimum amount, applied for this rule.")
    condition_range_max = fields.Float(string='Maximum Range', required=False, help="The maximum amount, applied for this rule.")
    amount_select = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('fix', 'Fixed Amount'),
        ('code', 'Python Code'),
    ], string='Amount Type', default='fix', select=True, required=True, help="The computation method for the rule amount.")
    amount_fix = fields.Float(string='Fixed Amount', digits_compute=dp.get_precision('Payroll'), default=0.0)
    amount_percentage = fields.Float(string='Percentage (%)', digits_compute=dp.get_precision('Payroll Rate'), default=0.0, help='For example, enter 50.0 to apply a percentage of 50%')
    amount_python_compute = fields.Text(string='Python Code')
    amount_percentage_base = fields.Char(string='Percentage based on', required=False, readonly=False, help='result will be affected to a variable')
    child_ids = fields.One2many('hr.salary.rule', 'parent_rule_id', string='Child Salary Rule', copy=True)
    register_id = fields.Many2one('hr.contribution.register', string='Contribution Register', help="Eventual third party involved in the salary payment of the employees.")
    input_ids = fields.One2many('hr.rule.input', 'input_id', string='Inputs', copy=True)
    note = fields.Text(string='Description')

    _defaults = {
        'amount_python_compute': '''
# Available variables:
#----------------------
# payslip: object containing the payslips
# employee: hr.employee object
# contract: hr.contract object
# rules: object containing the rules code (previously computed)
# categories: object containing the computed salary rule categories (sum of amount of all rules belonging to that category).
# worked_days: object containing the computed worked days.
# inputs: object containing the computed inputs.

# Note: returned value have to be set in the variable 'result'

result = contract.wage * 0.10''',
        'condition_python':
        '''
# Available variables:
#----------------------
# payslip: object containing the payslips
# employee: hr.employee object
# contract: hr.contract object
# rules: object containing the rules code (previously computed)
# categories: object containing the computed salary rule categories (sum of amount of all rules belonging to that category).
# worked_days: object containing the computed worked days
# inputs: object containing the computed inputs

# Note: returned value have to be set in the variable 'result'

result = rules.NET > categories.NET * 0.10''',
    }

    @api.multi
    def _recursive_search_of_rules(self, rule_ids):
        """
        @param rule_ids: list of browse record
        @return: returns a list of tuple (id, sequence) which are all the children of the passed rule_ids
        """
        children_rules = []
        for rule in rule_ids:
            if rule.child_ids:
                children_rules += self._recursive_search_of_rules(rule.child_ids)
        return [(r.id, r.sequence) for r in rule_ids] + children_rules

    #TODO should add some checks on the type of result (should be float)
    @api.model
    def compute_rule(self, rule_id, localdict):
        """
        :param rule_id: id of rule to compute
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        rule = self.browse(rule_id)
        if rule.amount_select == 'fix':
            try:
                return rule.amount_fix, float(eval(rule.quantity, localdict)), 100.0
            except:
                raise UserError(
                    _('Wrong quantity defined for salary rule %s (%s).') % (rule.name, rule.code))
        elif rule.amount_select == 'percentage':
            try:
                return (float(eval(rule.amount_percentage_base, localdict)),
                        float(eval(rule.quantity, localdict)),
                        rule.amount_percentage)
            except:
                raise UserError(_('Wrong percentage base or quantity defined for salary rule %s (%s).') % (
                    rule.name, rule.code))
        else:
            try:
                eval(
                    rule.amount_python_compute, localdict, mode='exec', nocopy=True)
                return float(localdict['result']), 'result_qty' in localdict and localdict['result_qty'] or 1.0, 'result_rate' in localdict and localdict['result_rate'] or 100.0
            except:
                raise UserError(_('Wrong python code defined for salary rule %s (%s).') % (
                    rule.name, rule.code))

    def satisfy_condition(self, rule_id, localdict):
        """
        @param rule_id: id of hr.salary.rule to be tested
        @param contract_id: id of hr.contract to be tested
        @return: returns True if the given rule match the condition for the given contract. Return False otherwise.
        """
        rule = self.browse(rule_id)

        if rule.condition_select == 'none':
            return True
        elif rule.condition_select == 'range':
            try:
                result = eval(rule.condition_range, localdict)
                return rule.condition_range_min <=  result and result <= rule.condition_range_max or False
            except:
                raise UserError(_('Wrong range condition defined for salary rule %s (%s).') % (
                    rule.name, rule.code))
        else: #python code
            try:
                eval(rule.condition_python, localdict, mode='exec', nocopy=True)
                return 'result' in localdict and localdict['result'] or False
            except:
                raise UserError(_('Wrong python condition defined for salary rule %s (%s).') % (
                    rule.name, rule.code))


class HrRuleInput(models.Model):
    '''
    Salary Rule Input
    '''

    _name = 'hr.rule.input'
    _description = 'Salary Rule Input'

    name = fields.Char(string='Description', required=True)
    code = fields.Char(size=52, required=True, help="The code that can be used in the salary rules")
    input_id = fields.Many2one('hr.salary.rule', string='Salary Rule Input', required=True)


class HrPayslipLine(models.Model):
    '''
    Payslip Line
    '''

    _name = 'hr.payslip.line'
    _inherit = 'hr.salary.rule'
    _description = 'Payslip Line'
    _order = 'contract_id, sequence'

    @api.one
    @api.depends('quantity', 'amount', 'rate')
    def _calculate_total(self):
        self.total = float(self.quantity) * self.amount * self.rate / 100

    slip_id = fields.Many2one(
        'hr.payslip', string='Pay Slip', required=True, ondelete='cascade')
    salary_rule_id = fields.Many2one(
        'hr.salary.rule', string='Rule', required=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True)
    contract_id = fields.Many2one(
        'hr.contract', string='Contract', required=True, select=True)
    rate = fields.Float(
        string='Rate (%)', digits=dp.get_precision('Payroll Rate'), default=100.0)
    amount = fields.Float(digits=dp.get_precision('Payroll'))
    quantity = fields.Float(digits=dp.get_precision('Payroll'), default=1.0)
    total = fields.Float(compute='_calculate_total',
                         digits=dp.get_precision('Payroll'), store=True)
