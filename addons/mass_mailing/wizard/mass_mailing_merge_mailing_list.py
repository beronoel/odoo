# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MailMergeMailingList(models.TransientModel):
    _name = 'mail.merge.mailing.list'
    _description = 'Merge Mailing Lists'

    mailing_list_ids = fields.Many2many('mail.mass_mailing.list', string='Massmail List')
    dst_massmail_list_id = fields.Many2one('mail.mass_mailing.list', string='Destination Mailing List')
    remove_duplicate = fields.Boolean('Remove Duplicates')

    @api.model
    def default_get(self, fields):
        """
        Use active_ids from the context to fetch the mailing list to merge.
        """
        res = super(MailMergeMailingList, self).default_get(fields)
        if self.env.context.get('active_model') == 'mail.mass_mailing.list' and self.env.context.get('active_ids'):
            mailing_list_ids = self.env.context['active_ids']
            res['mailing_list_ids'] = mailing_list_ids
            res['dst_massmail_list_id'] = mailing_list_ids[0]
        return res

    @api.multi
    def action_massmail_merge(self):
        if not self.dst_massmail_list_id:
            raise UserError(_('Please select destination mailing list.'))
        self.dst_massmail_list_id.merge_massmail_list(self.mailing_list_ids, self.remove_duplicate)
