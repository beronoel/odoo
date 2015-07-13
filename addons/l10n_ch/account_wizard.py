# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Author: Nicolas Bessi. Copyright Camptocamp SA
# Financial contributors: Hasa SA, Open Net SA,
#                         Prisme Solutions Informatique SA, Quod SA
# Translation contributors: brain-tec AG, Agile Business Group

from openerp.osv.orm import TransientModel

class WizardMultiChartsAccounts(TransientModel):

    _inherit ='wizard.multi.charts.accounts'

    def onchange_chart_template_id(self):
        res = super(WizardMultiChartsAccounts, self).onchange_chart_template_id()
        # 0 is evaluated as False in python so we have to do this
        # because original wizard test code_digits value on a float widget
        if self.chart_template_id:
            sterchi_template = self.env.ref('l10n_ch.l10nch_chart_template')
            if sterchi_template.id == self.chart_template_id.id:
                self.code_digits = 0
