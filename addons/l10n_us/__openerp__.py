# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'United States - Chart of accounts',
    'version': '1.1',
    'author': 'Odoo S.A.',
    'category': 'Localization/Account Charts',
    'description': """
United States - Chart of accounts.
==================================
    """,
    'website': 'http://www.odoo.com',
    'depends': ['l10n_generic_coa'],
    'data': [
        'account_chart_template.xml',
        'account.account.template.csv',
        'account_tax_template.xml',
        'account_chart_template_after.xml',
        'account_chart_template.yml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
}
