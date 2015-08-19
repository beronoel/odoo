# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Margins by Products',
    'category': 'Sales Management',
    'description': """
Adds a reporting menu in products that computes sales, purchases, margins and other interesting indicators based on invoices.
=============================================================================================================================

The wizard to launch the report has several options to help you get the data you need.
""",
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/report_product_margin_views.xml',
        'views/product_views.xml',
    ],
}
