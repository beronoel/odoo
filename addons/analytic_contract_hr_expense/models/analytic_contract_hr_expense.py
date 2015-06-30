# -*- coding: utf-8 -*-

from openerp import api, fields, models, _


class AccountAnalyticAccount(models.Model):
    _name = "account.analytic.account"
    _inherit = "account.analytic.account"

    charge_expenses = fields.Boolean(string="Charge Expenses")
    expense_invoiced = fields.Float(string="Expenses invoiced", compute='_expense_invoiced_calc')
    expense_to_invoice = fields.Float(string="Expenses to invoice", compute='_expense_to_invoice_calc')
    remaining_expense = fields.Float(string="Remaining Expenses", compute='_remaining_expnse_calc')
    est_expenses = fields.Float(string="Estimation of Expenses to Invoice")
    ca_invoiced = fields.Float(string='Invoiced Amount', compute='_ca_invoiced_calc',
                                   help="Total customer invoiced amount for this account.")

    @api.multi
    def _expense_invoiced_calc(self):
        for account in self:
            account.expense_invoiced = 0.0
            Lines = self.env['account.analytic.line']
            lines = Lines.search([('account_id', '=', account.id), ('invoice_id', '!=', False), (
                'to_invoice', '!=', False), ('journal_id.type', '=', 'purchase')])
            # Put invoices in separate array in order not to calculate them
            # double
            invoices = []
            for line in lines:
                if line.invoice_id not in invoices:
                    invoices.append(line.invoice_id)
            for invoice in invoices:
                account.expense_invoiced += invoice.amount_untaxed
    
    @api.multi
    def _expense_to_invoice_calc(self):
        # We don't want consolidation for each of these fields because those
        # complex computation is resource-greedy.
        for account in self:
            self.env.cr.execute("""
                SELECT product_id, sum(amount), user_id, to_invoice, sum(unit_amount), product_uom_id, line.name
                FROM account_analytic_line line
                    LEFT JOIN account_analytic_journal journal ON (journal.id = line.journal_id)
                WHERE account_id = %s
                    AND journal.type = 'purchase'
                    AND invoice_id IS NULL
                    AND to_invoice IS NOT NULL
                GROUP BY product_id, user_id, to_invoice, product_uom_id, line.name""", (account.id,))

            account.expense_to_invoice = 0.0
            for product_id, total_amount, user_id, factor_id, qty, uom, line_name in self.env.cr.fetchall():
                # the amount to reinvoice is the real cost. We don't use the
                # pricelist
                total_amount = -total_amount
                factor = self.env['hr_timesheet_invoice.factor'].browse(factor_id)
                account.expense_to_invoice += total_amount * \
                    (100 - factor.factor or 0.0) / 100.0

    @api.depends('est_expenses','expense_invoiced','expense_to_invoice')
    def _remaining_expnse_calc(self):
        for account in self:
            if account.est_expenses != 0:
                account.remaining_expense = max(
                    account.est_expenses - account.expense_invoiced, account.expense_to_invoice)
            else:
                account.remaining_expense = 0.0

    @api.depends('expense_invoiced')
    def _ca_invoiced_calc(self, name=None, arg=None):
        result = super(AccountAnalyticAccount, self)._ca_invoiced_calc(name, arg)
        for account in self:
            account.ca_invoiced -= account.expense_invoiced

    @api.multi
    def on_change_template(self, template_id, date_start=False):
        res = super(AccountAnalyticAccount, self).on_change_template(
            template_id, date_start=date_start)
        if template_id and 'value' in res:
            template = self.browse(template_id)
            res['value']['charge_expenses'] = template.charge_expenses
            res['value']['est_expenses'] = template.est_expenses
        return res

    @api.multi
    def open_hr_expense(self):
        self.ensure_one()
        result = self.env.ref('hr_expense.expense_all').read()[0]
        lines = self.env['hr.expense.line'].search([('analytic_account', 'in', self.ids)])
        result['domain'] = [('line_ids', 'in', lines.ids)]
        result['name'] = _('Expenses of %s') % self.name
        result['context'] = {'analytic_account': self.ids[0]}
        result['view_type'] = 'form'
        return result
                    
    @api.multi
    def hr_to_invoice_expense(self):
        domain = [('invoice_id', '=', False), ('to_invoice', '!=', False),
                  ('journal_id.type', '=', 'purchase'), ('account_id', 'in', self.ids)]
        names = [record.name for record in self]
        name = _('Expenses to Invoice of %s') % ','.join(names)
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain': domain,
            'res_model': 'account.analytic.line',
            'nodestroy': True,
        }

    def _get_total_estimation(self, account):
        tot_est = super(AccountAnalyticAccount, self)._get_total_estimation(account)
        if account.charge_expenses:
            tot_est += account.est_expenses
        return tot_est

    def _get_total_invoiced(self, account):
        total_invoiced = super(AccountAnalyticAccount, self)._get_total_invoiced(account)
        if account.charge_expenses:
            total_invoiced += account.expense_invoiced
        return total_invoiced

    def _get_total_remaining(self, account):
        total_remaining = super(AccountAnalyticAccount, self)._get_total_remaining(account)
        if account.charge_expenses:
            total_remaining += account.remaining_expense
        return total_remaining

    def _get_total_toinvoice(self, account):
        total_toinvoice = super(AccountAnalyticAccount, self)._get_total_toinvoice(account)
        if account.charge_expenses:
            total_toinvoice += account.expense_to_invoice
        return total_toinvoice
