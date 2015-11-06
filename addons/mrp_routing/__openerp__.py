# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Shared Routing',
    'version': '1.1',
    'website': 'https://www.odoo.com/page/manufacturing',
    'category': 'Manufacturing',
    'sequence': 14,
    'summary': 'Defined shared routing for your BoMs',
    'depends': ['mrp'],
    'description': """
Shared Routing for Bill of Material
===================================

Use this module to define routing, as a list of operations done in workcenters, in order to reuse the same routing into several BoMs. That allows you to repercut the changes done on a routing, on all the BoM where it is used.

    """,
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
