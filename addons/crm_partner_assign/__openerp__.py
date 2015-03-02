# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Partner Assignation & Geolocation',
    'version': '1.0',
    'category': 'Customer Relationship Management',
    'description': """
This is the module used by Odoo S.A. to redirect customers to its partners, based on geolocation.
======================================================================================================

This modules lets you geolocate Leads, Opportunities and Partners based on their address.

Once the coordinates of the Lead/Opportunity is known, they can be automatically assigned
to an appropriate local partner, based on the distance and the weight that was assigned to the partner.
    """,
    'author': 'Odoo S.A.',
    'website': 'https://www.odoo.com',
    'depends': ['base_geolocalize', 'crm', 'account', 'portal'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_view.xml',
        'wizard/crm_forward_to_partner_view.xml',
        'wizard/crm_channel_interested_view.xml',
        'views/crm_lead_view.xml',
        'data/crm_partner_assign_data.xml',
        'views/crm_portal_view.xml',
        'data/portal_data.xml',
        'report/crm_lead_report_view.xml',
        'report/crm_partner_report_view.xml',
    ],
    'demo': [
        'data/res_partner_demo.xml',
        'data/crm_lead_demo.xml'
    ],
    'installable': True,
}
