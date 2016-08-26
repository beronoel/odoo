# -*- coding: utf-8 -*-
{
    'name': "Members check-in system",

    'summary': """
        This module implements a web-based system for members check-in, based on a unique identification number.""",

    'description': """
        Long description of module's purpose
    """,

    'author': "PolyFab",
    'website': "http://polyfab.polymtl.ca/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['website'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}