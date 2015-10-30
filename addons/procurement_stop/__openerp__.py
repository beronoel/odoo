# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name' : 'Manual Decision on Procurements',
    'version' : '1.0',
    'website': 'https://www.odoo.com/page/manufacturing',
    'category' : 'Hidden/Dependency',
    'depends' : ['procurement'],
    'description': """
This lets users take a decision on the different procurements
    """,
    'data': ['views/procurement_view.xml'],
    'demo': [],
    'test': [],
    'installable': True,
}
