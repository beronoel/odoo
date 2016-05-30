{
    'name': 'Web Backend Editor',
    'category': 'Hidden',
    'description': """
Odoo Web Backend Editor
========================
Add field, move field, remove field and customise fields in the backend
for the form and list views

""",
    'author': 'Odoo S.A.',
    'depends': ['web'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],
    'auto_install': False
}
