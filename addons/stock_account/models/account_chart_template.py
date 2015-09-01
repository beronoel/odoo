# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from openerp import api, models, _

_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.Model):
    _inherit = "account.chart.template"

    @api.model
    def generate_journals(self, acc_template_ref, company, journals_dict=None):
        journal_to_add = [{'name': _('Stock Journal'), 'type': 'general', 'code': 'STJ', 'favorite': False, 'sequence': 8}]
        super(AccountChartTemplate, self).generate_journals(acc_template_ref=acc_template_ref, company=company, journals_dict=journal_to_add)

    @api.multi
    def generate_properties(self, acc_template_ref, company, property_list=None):
        self.ensure_one()
        super(AccountChartTemplate, self).generate_properties(acc_template_ref=acc_template_ref, company=company)
        IrProperty = self.env['ir.property']
        IrModelFields = self.env['ir.model.fields']
        journal = self.env['account.journal'].search([('company_id', '=', company.id), ('code', '=', 'STJ'), ('type', '=', 'general')], limit=1)
        if journal:
            field = IrModelFields.search([('name', '=', 'property_stock_journal_id'), ('model', '=', 'product.category'), ('relation', '=', 'account.journal')], limit=1)
            vals = {
                'name': 'property_stock_journal_id',
                'company_id': company.id,
                'fields_id': field.id,
                'value': journal,
            }
            properties = IrProperty.search([('name', '=', 'property_stock_journal_id'), ('company_id', '=', company.id)])
            if properties:
                #the property exist: modify it
                properties.write(vals)
            else:
                #create the property
                IrProperty.create(vals)

        todo_list = [ # Property Stock Accounts
            'property_stock_account_input_categ_id',
            'property_stock_account_output_categ_id',
            'property_stock_valuation_account_id',
        ]
        for record in todo_list:
            account = getattr(self, record)
            value = account and acc_template_ref[account.id] or False
            if value:
                field = IrModelFields.search([('name', '=', record), ('model', '=', 'product.category'), ('relation', '=', 'account.account')], limit=1)
                vals = {
                    'name': record,
                    'company_id': company.id,
                    'fields_id': field.id,
                    'value': value,
                    'res_id': self.env.ref('product.product_category_all').id,
                }
                properties = IrProperty.search([('name', '=', record), ('company_id', '=', company.id)])
                if properties:
                    #the property exist: modify it
                    properties.write(vals)
                else:
                    #create the property
                    IrProperty.create(vals)

        return True
