# -*- coding: utf-8 -*-

{
    'name': 'Buckaroo Payment Acquirer',
    'category': 'Extra Tools',
    'summary': 'Payment Acquirer: Buckaroo Implementation',
    'version': '1.0',
    'description': """Buckaroo Payment Acquirer""",
    'depends': ['payment'],
    'data': [
        'views/buckaroo.xml',
        'views/payment_acquirer.xml',
        'data/buckaroo.xml',
    ],
    'installable': True,
}
