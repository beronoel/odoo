# -*- coding: utf-8 -*-

from openerp import api, fields, models, _


class Notification(models.Model):
    _name = 'mail.notification'
    _table = 'mail_message_res_partner_needaction_rel'
    _rec_name = 'res_partner_id'
    _log_access = False
    _description = 'Message Notifications'

    mail_message_id = fields.Many2one(
        'mail.message', 'Message', index=True, required=True, ondelete='cascade')
    res_partner_id = fields.Many2one(
        'res.partner', 'Needaction Recipient', index=True, required=True, ondelete='cascade')
    is_read = fields.Boolean('Is Read', index=True)
    is_email = fields.Boolean('Sent by Email')
    email_state = fields.Selection([
        ('ready', 'Ready to Send'),
        ('sent', 'Sent'),
        ('bounce', 'Bounced'),
        ('exception', 'Exception')], 'Email Status')  # email_status ?
