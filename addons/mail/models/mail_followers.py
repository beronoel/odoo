# -*- coding: utf-8 -*-

from openerp import api, fields, models

import uuid

class Followers(models.Model):
    """ mail_followers holds the data related to the follow mechanism inside
    Odoo. Partners can choose to follow documents (records) of any kind
    that inherits from mail.thread. Following documents allow to receive
    notifications for new messages. A subscription is characterized by:

    :param: res_model: model of the followed objects
    :param: res_id: ID of resource (may be 0 for every objects)
    """
    _name = 'mail.followers'
    _rec_name = 'partner_id'
    _log_access = False
    _description = 'Document Followers'

    res_model = fields.Char(
        'Related Document Model', required=True, select=1, help='Model of the followed resource')
    res_id = fields.Integer(
        'Related Document ID', select=1, help='Id of the followed resource')
    partner_id = fields.Many2one(
        'res.partner', string='Related Partner', ondelete='cascade', required=True, select=1)
    subtype_ids = fields.Many2many(
        'mail.message.subtype', string='Subtype',
        help="Message subtypes followed, meaning subtypes that will be pushed onto the user's Wall.")

    #
    # Modifying followers change access rights to individual documents. As the
    # cache may contain accessible/inaccessible data, one has to refresh it.
    #
    @api.model
    def create(self, vals):
        res = super(Followers, self).create(vals)
        self.invalidate_cache()
        return res

    @api.multi
    def write(self, vals):
        res = super(Followers, self).write(vals)
        self.invalidate_cache()
        return res

    @api.multi
    def unlink(self):
        res = super(Followers, self).unlink()
        self.invalidate_cache()
        return res

    _sql_constraints = [('mail_followers_res_partner_res_model_id_uniq', 'unique(res_model,res_id,partner_id)', 'Error, a partner cannot follow twice the same object.')]


class Notification(models.Model):
    """ Class holding notifications pushed to partners. Followers and partners
    added in 'contacts to notify' receive notifications. """
    _name = 'mail.notification'
    _rec_name = 'partner_id'
    _log_access = False
    _description = 'Notifications'

    partner_id = fields.Many2one('res.partner', string='Contact', ondelete='cascade', required=True, select=1)
    is_read = fields.Boolean('Read', select=1, oldname='read')
    starred = fields.Boolean('Starred', select=1, help='Starred message that goes into the todo mailbox')
    message_id = fields.Many2one('mail.message', string='Message', ondelete='cascade', required=True, select=1)

    def init(self, cr):
        cr.execute('SELECT indexname FROM pg_indexes WHERE indexname = %s', ('mail_notification_partner_id_read_starred_message_id',))
        if not cr.fetchone():
            cr.execute('CREATE INDEX mail_notification_partner_id_read_starred_message_id ON mail_notification (partner_id, is_read, starred, message_id)')

    def get_partners_to_email(self, message):
        """ Return the list of partners to notify, based on their preferences.

            :param browse_record message: mail.message to notify
            :param list partners_to_notify: optional list of partner ids restricting
                the notifications to process
        """
        notify_partners = self.env['res.partner']
        for notification in self:
            if notification.is_read:
                continue
            partner = notification.partner_id
            # Do not send to partners without email address defined
            if not partner.email:
                continue
            # Do not send to partners having same email address than the author (can cause loops or bounce effect due to messy database)
            if message.author_id and message.author_id.email == partner.email:
                continue
            # Partner does not want to receive any emails or is opt-out
            if partner.notify_email == 'none':
                continue
            notify_partners |= partner
        return notify_partners

    def update_message_notification(self, message, partners):
        # update existing notifications
        self.write({'is_read': False})

        # create new notifications
        new_notif_ids = self.env['mail.notification']
        for new_pid in partners - self.mapped('partner_id'):
            new_notif_ids |= self.create({'message_id': message.id, 'partner_id': new_pid.id, 'is_read': False})
        return new_notif_ids

    @api.multi
    def _notify_email(self, message, force_send=False, user_signature=True):
        email_partners = self.get_partners_to_email(message)
        if not email_partners:
            return True
        return email_partners.message_send_notification_email(message, force_send=force_send, user_signature=user_signature)

    @api.model
    def _notify(self, message, recipients=None, force_send=False, user_signature=True):
        """ Send by email the notification depending on the user preferences

            :param list partners_to_notify: optional list of partner ids restricting
                the notifications to process
            :param bool force_send: if True, the generated mail.mail is
                immediately sent after being created, as if the scheduler
                was executed for this message only.
            :param bool user_signature: if True, the generated mail.mail body is
                the body of the related mail.message with the author's signature
        """
        # browse as SUPERUSER_ID because of access to res_partner not necessarily allowed
        notif_ids = self.sudo().search([('message_id', '=', message.id), ('partner_id', 'in', recipients.ids)])

        # update or create notifications
        new_notif_ids = notif_ids.update_message_notification(message, recipients)  # tde check: sudo

        # mail_notify_noemail (do not send email) or no partner_ids: do not send, return
        if self.env.context.get('mail_notify_noemail'):
            return True

        return new_notif_ids._notify_email(message, force_send, user_signature)  # tde check this one too


class FollowersMailAction(models.Model):
    """
    FollowersMailAction holds the data related to Authentication for
    unfollow mechanism and performing actions directly from mail action
    buttons inside Odoo. Record will be created per partner per document
    while posting in chatter only for those partners who has related user
    (and so login credentials) and follows particular document.
    """
    _name = 'mail.followers.action'
    _description = 'Followers Authentication'

    res_model = fields.Char(
        string='Related Document Model', required=True, help='Model of the followed resource')
    res_id = fields.Integer(
        string='Related Document ID', required=True, help='Id of the followed resource')
    partner_id = fields.Many2one('res.partner', string='Contact', ondelete='cascade', required=True)
    token = fields.Char(required=True, help='Unique token', default=uuid.uuid4().__str__())
    # state = fields.Selection([('cancelled', 'Cancelled'), ('draft', 'Draft'), ('closed', 'Closed')],
    #                          'Status', required=True, readonly=True, copy=False, default="draft",
    #                          help='* The \'Draft\' status is set by default. \
    #                 \n* The \'Cancelled\' status is set user unfollows the document. \
    #                 \n* The \'Closed\' status is set when the action is perfomed successfully.')
    # [DJA] Right now I don't feel need of the state field on this model.
