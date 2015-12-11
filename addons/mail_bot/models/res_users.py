# -*- coding: utf-8 -*-

from openerp import _, api, fields, models
import openerp


class Users(models.Model):
    """ Update of res.users class
        - Send a welcome direct message on newly created users
    """
    _name = 'res.users'
    _inherit = ['res.users']

    @api.model
    def create(self, values):
        user = super(Users, self).create(values)
        bot_partner = self.env['ir.model.data'].xmlid_to_object('base.res_partner_bot')
        mail_channel = self.env['mail.channel'].sudo().create({'name': user.partner_id.name + u', ' + bot_partner.name, 'public': 'private', 'channel_type': 'chat', 'channel_partner_ids': [(6, 0, [bot_partner.id, user.partner_id.id])], }) 
        body = "<p>" + _("Hello, My name is Jack Bot. I here to help you discover Odoo Discuss. (Be kind with me, I’m still just a bot after all!) Type ​<b>something</b>​ to get started.") + "</p>"
        mail_channel.message_post(
            author_id=bot_partner.id,
            body=body, subject="User Creation Message",
            subtype='mail.mt_comment')
        return user
