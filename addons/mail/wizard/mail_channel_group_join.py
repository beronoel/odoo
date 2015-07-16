# -*- coding: utf-8 -*-
from openerp import api, fields, models
from openerp import _


class MailChannelJoin(models.TransientModel):
    _name = "mail.channel.group.join"
    _description = "Join Channel Gourp Wizard"

    def _default_member_channel_ids(self):
        channels = self.env['mail.channel'].search([('channel_partner_ids', 'in', [self.env.user.partner_id.id]), ('channel_type', 'not in', ['chat', 'personal'])])
        return [(4, channel_id) for channel_id in channels.ids]

    def _default_open_channel_ids(self):
        channels = self.env['mail.channel'].search([('channel_partner_ids', 'not in', [self.env.user.partner_id.id]), ('channel_type', 'not in', ['chat', 'personal'])])
        return [(4, channel_id) for channel_id in channels.ids]

    # this should be a One2Many, but One2Many computed doesn't work very well.
    member_channel_ids = fields.Many2many(string="You are a member of", comodel_name='mail.channel', default=_default_member_channel_ids)
    open_channel_ids = fields.Many2many(string="You can join", comodel_name='mail.channel', default=_default_open_channel_ids)

    @api.multi
    def action_create_channel(self):
        self.ensure_one()
        return {
            'name': _('Create channel'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.channel',
            'type': 'ir.actions.act_window',
            'context': self.env.context,
            'target': 'new'
        }
