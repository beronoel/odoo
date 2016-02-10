# -*- coding: utf-8 -*-

from openerp import _, api, models

class Channel(models.Model):
    """ Update of res.users class
        - Send a welcome direct message on newly created users
    """
    _name = 'mail.channel'
    _inherit = ['mail.channel']
    _bot_conversation = {}    
    
    bot_messages_intro = [
        "<p>" + _("Hi! Pleasure to meet you. I can show you a couple things. Type <b>something</b> again to know more!") + "<p>",

        "<p>" + _("We you're ready, click on this link to ") + "<a class='o_mail_chat_button_tour'>" + _("Explore Odoo Discuss!") + "</a></p>" + \
        "<p>" + _("Also visit our ") + "<a href='https://www.odoo.com/documentation/user/' target='_blank'>User Documentation</a>" + _(" if you ever get lost or want some more informations about Odoo.") + "</p>" + \
        "<p>" + _("Type <b>help</b> if you need more information") + "</p>" + \
        "<p>" + _("Otherwise, have a wonderful day, and welcome to Odoo! :postal_horn") + "</p>"
    ]

    @api.multi
    @api.returns('self', lambda value: value.id)
    def message_post(self, body='', subject=None, message_type='notification', subtype=None, parent_id=False, attachments=None, content_subtype='html', **kwargs):
        message = super(Channel, self).message_post(body=body, subject=subject, message_type=message_type, subtype=subtype, parent_id=parent_id, attachments=attachments, content_subtype=content_subtype, **kwargs)
        # If it is a direct message from a partner to the bot partner
        if self.public == 'private' and self.channel_type == 'chat':
            partner_ids = self.channel_partner_ids
            bot_partner_id = self.env['ir.model.data'].xmlid_to_object('base.res_partner_bot')
            author_id = kwargs.get('author_id', False) 
            if bot_partner_id.id in partner_ids.ids and not (author_id and author_id == bot_partner_id.id):
                self._bot_conversation.setdefault(self.env.uid, ('intro', 0))
                # Pick a conversion (will reset the previous if something found)
                self._bot_message(body, bot_partner_id.id)
        return message

    @api.model
    def _bot_message(self, body='', author_id=None):
        # Options management
        if body == 'ping':
            self._bot_message_post('pong', author_id)
        elif body == 'intro':
            self._bot_conversation[self.env.uid] = ('intro', 0)
        elif body == 'help':
            bot_message_body = "<p>" + _("If you have other questions about Odoo, you might find the answer in our ") + "<a href='https://www.odoo.com/documentation/user/' target='_blank'>User Documentation</a>" + "</p>" + \
                   "<p>" + _("And if you would like to get in touch with one Odoo collaborator, please ") + "<a href='https://www.odoo.com/page/contactus' target='_blank'>" + _("Contact Us!") + "</a></p>"
            self._bot_message_post(bot_message_body, author_id)

        # 'Intro' conversation management
        if self._bot_conversation[self.env.uid][0] == 'intro' and self._bot_conversation[self.env.uid][1] < len(self.bot_messages_intro):
            bot_message_body = self.bot_messages_intro[self._bot_conversation[self.env.uid][1]]
            self._bot_message_post(bot_message_body, author_id)
            self._bot_conversation[self.env.uid] = (self._bot_conversation[self.env.uid][0], self._bot_conversation[self.env.uid][1] + 1)

    @api.multi
    @api.returns('self', lambda value: value.id)
    def _bot_message_post(self, body='', author_id=None):
        # Send next message
        bot_message = self.message_post(
            author_id=author_id, 
            body=body, 
            subject='Bot Message',
            subtype='mail.mt_comment')
        return bot_message
