# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Mail Bot',
    'category': 'Usability',
    'description': """
Odoo bot for mail module.
=========================

""",
    'version': '0.1',
    'depends': ['mail'],
    'data': [
        'data/mail_bot_data.xml',
    ],
    'auto_install': True
}
