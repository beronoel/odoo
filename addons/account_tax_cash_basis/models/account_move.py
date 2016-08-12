# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields


class AccountMoveCashBasis(models.Model):
    _inherit = 'account.move'

    tax_cash_basis_rec_id = fields.Many2one(
        'account.partial.reconcile',
        string='Tax Cash Basis Entry of',
        help="Technical field used to keep track of the tax cash basis reconciliation."
        "This is needed when cancelling the source: it will post the inverse journal entry to cancel that part too.")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def create(self, vals, apply_taxes=True):
        tax = False
        if vals.get('tax_line_id'):
            tax = self.env['account.tax'].browse(vals['tax_line_id'])
        if vals.get('tax_ids'):
            tax = self.env['account.tax'].browse(vals['tax_ids'])
        if tax and tax.use_cash_basis and not vals.get('tax_exigible'):
            vals['tax_exigible'] = False
        return super(AccountMoveLine, self).create(vals, apply_taxes=apply_taxes)
