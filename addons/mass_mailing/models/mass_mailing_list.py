# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MassMailingList(models.Model):
    _inherit = 'mail.mass_mailing.list'

    recipient_ids = fields.One2many('mail.mass_mailing.contact', 'list_id', string='Recipients', copy=True, domain=[('opt_out', '=', False)])

    @api.multi
    def merge_massmail_list(self, mailing_lists, remove_duplicates=False):
        self.ensure_one()
        if len(mailing_lists) <= 1 and self in mailing_lists or not mailing_lists:
            raise UserError(_('Please select more than one massmail list from the list view.'))
        mailing_lists = mailing_lists.filtered(lambda mailing_list: mailing_list.id != self.id)
        merge_recipients = mailing_lists.mapped('recipient_ids')
        if remove_duplicates:
            merge_recipients = self._filtered_duplicate_recipients(merge_recipients)
        for merge_recipient in merge_recipients:
            merge_recipient.copy({'list_id': self.id})

    def _filtered_duplicate_recipients(self, recipients):
        emails = self.recipient_ids.mapped('email')
        merge_recipients = []
        for recipient in recipients:
            if recipient.email not in emails:
                emails.append(recipient.email)
                merge_recipients.append(recipient)
        return merge_recipients
