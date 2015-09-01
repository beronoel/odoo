# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _


class WizardValuationHistory(models.TransientModel):
    _name = 'wizard.valuation.history'
    _description = 'Wizard that opens the stock valuation history table'

    choose_date = fields.Boolean('Inventory at Date', default=False)
    valuation_date = fields.Datetime('Date', required=True, default=fields.Datetime.now())

    @api.multi
    def open_table(self):
        self.ensure_one()
        data = self.read()[0]
        ctx = self.env.context.copy()
        ctx['history_date'] = data['valuation_date']
        ctx['search_default_group_by_product'] = True
        ctx['search_default_group_by_location'] = True
        return {
            'domain': "[('operation_date', '<=', '" + data['valuation_date'] + "')]",
            'name': _('Stock Value At Date'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.history',
            'type': 'ir.actions.act_window',
            'context': ctx,
        }
