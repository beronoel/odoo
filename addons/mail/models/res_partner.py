# -*- coding: utf-8 -*-

from openerp import _, api, fields, models


class Partner(models.Model):
    """ Update partner to add a field about notification preferences. Add a generic opt-out field that can be used
       to restrict usage of automatic email templates. """
    _name = "res.partner"
    _inherit = ['res.partner', 'mail.thread']
    _mail_flat_thread = False
    _mail_mass_mailing = _('Customers')

    notify_email = fields.Selection([
        ('none', 'Never'),
        ('always', 'All Messages')],
        'Email Messages and Notifications', required=True,
        oldname='notification_email_send', default='always',
        help="Policy to receive emails for new messages pushed to your personal Inbox:\n"
             "- Never: no emails are sent\n"
             "- All Messages: for every notification you receive in your Inbox")
    opt_out = fields.Boolean(
        'Opt-Out', help="If opt-out is checked, this contact has refused to receive emails for mass mailing and marketing campaign. "
                        "Filter 'Available for Mass Mailing' allows users to filter the partners when performing mass mailing.")

    @api.multi
    def message_get_suggested_recipients(self):
        recipients = super(Partner, self).message_get_suggested_recipients()
        for partner in self:
            partner._message_add_suggested_recipient(recipients, partner=partner, reason=_('Partner Profile'))
        return recipients

    @api.multi
    def message_get_default_recipients(self):
        return dict((res_id, {'partner_ids': [res_id], 'email_to': False, 'email_cc': False}) for res_id in self.ids)

    @api.multi
    def message_send_notification_email(self, message, force_send=False, user_signature=True):
        """ Method to send email linked to notified messages.

        UPDATE ME """
        # rebrowse as sudo to avoid access rigths on author, user, ... -> portal / public goes through this method
        message_sudo = message.sudo()

        # compute signature
        signature = False
        if user_signature:
            if message_sudo.author_id and message_sudo.author_id.user_ids and message_sudo.author_id.user_ids[0].signature:
                signature = message_sudo.author_id.user_ids[0].signature
            elif message_sudo.author_id:
                signature = "<p>--<br />%s</p>" % message_sudo.author_id.name

        # compute Sent by
        if message_sudo.author_id and message_sudo.author_id.user_ids:
            user = message_sudo.author_id.user_ids[0]
        else:
            user = self.env.user
        if user.company_id.website:
            website_url = 'http://%s' % user.company_id.website if not user.company_id.website.lower().startswith(('http:', 'https:')) else user.company_id.website
        else:
            website_url = False
        company_name = user.company_id.name

        # compute email references
        references = message_sudo.parent_id.message_id if message_sudo.parent_id else False

        # custom values
        custom_values = dict()
        if message_sudo.model and message_sudo.res_id and self.pool.get(message_sudo.model) and hasattr(self.pool[message_sudo.model], 'message_get_email_values'):
            custom_values = self.env[message_sudo.model].browse(message_sudo.res_id).message_get_email_values(message_sudo)

        # prepare values for notification body rendering
        template_ctx = {
            'user_signature': user_signature,
            'signature': signature,
            'website_url': website_url,
            'company_name': company_name,
        }

        # classify recipients: actions / no action
        recipients = {}
        if message_sudo.model and message_sudo.res_id and hasattr(self.env[message_sudo.model], '_message_classify_recipients'):
            recipients = self.env[message_sudo.model].browse(message_sudo.res_id)._message_classify_recipients(message_sudo, self)
        # print recipients

        emails = self.env['mail.mail']

        for email_type, frite in recipients.iteritems():
            my_recipients = frite['recipients']
            # print 'generating for', email_type, 'with recipients', my_recipients

            # create body
            tpl = self.env.ref('mail.mail_default_notification_email')
            template_ctx.update(frite)
            tpl = tpl.with_context(**template_ctx)
            generated_values = tpl.generate_email(message.id, fields=['body_html', 'subject'])
            body = generated_values['body']
            subject = generated_values['subject']

            # create email values
            max_recipients = 50
            chunks = [my_recipients[x:x + max_recipients] for x in xrange(0, len(my_recipients), max_recipients)]

            for chunk in chunks:
                mail_values = {
                    'mail_message_id': message_sudo.id,
                    'auto_delete': self._context.get('mail_auto_delete', True),
                    'body_html': body,
                    'subject': subject,
                    'recipient_ids': [(4, partner.id) for partner in chunk],
                    'references': references,
                }
                mail_values.update(custom_values)
                emails |= self.env['mail.mail'].create(mail_values)

        # # NOTE:
        # #   1. for more than 50 followers, use the queue system
        # #   2. do not send emails immediately if the registry is not loaded,
        # #      to prevent sending email during a simple update of the database
        # #      using the command-line.
        # if force_send and len(chunks) < 2 and \
        #        (not self.pool._init or
        #         getattr(threading.currentThread(), 'testing', False)):
        #     emails.send()

        return True
