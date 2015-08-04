# -*- coding: utf-8 -*-

from openerp.osv import osv
from openerp.tools.safe_eval import safe_eval as eval
from openerp.addons.website.models.website import slug


class MailGroup(osv.Model):
    _inherit = 'mail.channel'

    def message_get_email_values(self, cr, uid, ids, notif_mail=None, context=None):
        assert len(ids) == 1, 'Values are always returned for single mail'
        res = super(MailGroup, self).message_get_email_values(cr, uid, ids, notif_mail=notif_mail, context=context)
        group = self.browse(cr, uid, ids, context=context)
        base_url = self.pool['ir.config_parameter'].get_param(cr, uid, 'web.base.url')
        headers = {}
        if res.get('headers'):
            try:
                headers = eval(res['headers'])
            except Exception:
                pass
        headers.update({
            'List-Archive': '<%s/groups/%s>' % (base_url, slug(group)),
            'List-Subscribe': '<%s/groups>' % (base_url),
            'List-Unsubscribe': '<%s/groups?unsubscribe>' % (base_url,),
        })
        res['headers'] = repr(headers)
        return res
