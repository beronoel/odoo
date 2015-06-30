# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Contracts Management: hr_expense link',
    'version': '2.0',
    'category': 'Hidden',
    'description': """
This module is for modifying account analytic view to show some data related to the hr_expense module.
======================================================================================================
""",
    'author': 'Odoo S.A.',
    'website': 'https://www.odoo.com/',
    'depends': ['hr_expense','account_analytic_analysis'],
    'data': ['views/analytic_contract_hr_expense_view.xml'],
    'demo': [],
    'installable': True,
}
