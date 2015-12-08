# -*- coding: utf-8 -*-

from openerp.osv import fields, osv 

class event_config_settings(osv.TransientModel):
    _name='event.config.settings'
    _inherit='res.config.settings'
    _columns = {
        'event_config_type': fields.selection([
            (1, 'All events are free'),
            (2, 'Allow selling tickets'),
            (3, 'Allow your customer to buy tickets from your eCommerce'),
            ], "Tickets",
            help='Install website_event_sale or event_sale module based on options'),
        'module_event_sale': fields.boolean(),
        'module_website_event_sale': fields.boolean(),
        'module_website_event_track': fields.selection([
            (0, "No mini website per event"),
            (1, 'Allow tracks, agenda and dedicated menus/website per event')
            ], "Tracks and Agenda",
            help='Install the module website_event_track'),
        'module_website_event_questions': fields.selection([
            (0, "No extra questions on registrations"),
            (1, 'Allow adding extra questions on registrations')
            ], "Registration Survey",
            help='Install the website_event_questions module'),
        'auto_confirmation': fields.selection([
            (1, 'No validation step on registration'),
            (0, "Manually confirm every registration")
            ], "Auto Confirmation",
            help='Unselect this option to manually manage draft event and draft registration'),
        'group_email_scheduling': fields.selection([
            (0, "No automated emails"),
            (1, 'Schedule emails to attendees and subscribers')
            ], "Email Scheduling",
            help='You will be able to configure emails, and to schedule them to be automatically sent to the attendees on subscription and/or attendance',
            implied_group='event.group_email_scheduling'),            
        'module_event_barcode': fields.boolean("Scan badges to confirm attendances",
            help="Install the event_barcode module"),
    }

    def default_get(self, cr, uid, fields, context=None):
        res = super(event_config_settings, self).default_get(cr, uid, fields, context)
        if 'event_config_type' in fields: res['event_config_type'] = 1
        if 'module_website_event_sale' in fields and res['module_website_event_sale']:
            res['event_config_type'] = 3
        elif 'module_event_sale' in fields and res['module_event_sale']:
            res['event_config_type'] = 2
        return res

    def onchange_event_config_type(self, cr, uid, ids, event_config_type, context=None):
        if event_config_type == 3:
            return {'value': {'module_website_event_sale': True}}
        elif event_config_type == 2:
            return {'value': {'module_event_sale': True, 'module_website_event_sale': False}}
        return {'value': {'module_event_sale': False, 'module_website_event_sale': False}}


    def set_default_event_config_type(self, cr, uid, ids, context=None):
        config_value = self.browse(cr, uid, ids, context=context).event_config_type
        self.pool['ir.values'].set_default(cr, uid, 'event.config.settings', 'event_config_type', config_value)

    def set_default_auto_confirmation(self, cr, uid, ids, context=None):
        config_value = self.browse(cr, uid, ids, context=context).auto_confirmation
        self.pool.get('ir.values').set_default(cr, uid, 'event.config.settings', 'auto_confirmation', config_value)
