{
    'name': 'Online Proposals',
    'category': 'Website',
    'summary': 'Send Professional Quotations',
    'website': 'https://www.odoo.com/page/quote-builder',
    'version': '1.0',
    'description': """
Odoo Sale Quote Roller
=========================

        """,
    'author': 'Odoo SA',
    'depends': ['website', 'sale', 'mail', 'web_tip', 'payment', 'website_portal'],
    'data': [
        'views/quotation_report.xml',
        'views/website_quotation.xml',
        'views/sale_order_views.xml',
        'views/sale_quote_template_views.xml',
        'views/report_saleorder.xml',
        'views/report_quotation.xml',
        'data/website_quotation_data.xml',
        'security/ir.model.access.csv',
        'data/quotation_tip_data.xml',
    ],
    'demo': [
        'data/website_quotation_demo.xml'
    ],
    'qweb': ['static/src/xml/*.xml'],
    'installable': True,
}
