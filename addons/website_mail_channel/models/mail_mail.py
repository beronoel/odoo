# -*- coding: utf-8 -*-

from openerp.osv import osv
from openerp import tools
from openerp.tools.translate import _
from openerp.addons.website.models.website import slug


class MailMail(osv.Model):
    _inherit = 'mail.mail'

    def send_get_mail_body(self, cr, uid, ids, partner=None, context=None):
        """ Short-circuit parent method for mail groups, replace the default
            footer with one appropriate for mailing-lists."""
        # TDE: temporary addition (mail was parameter) due to semi-new-API
        mail = self.browse(cr, uid, ids[0], context=context)

        if mail.model == 'mail.channel' and mail.res_id:
            mail_follower = self.pool['mail.followers']
            mail_follower_id = mail_follower.search(cr, uid, [('partner_id', '=', partner and partner.id or False), ('res_id', '=', mail.res_id), ('res_model', '=', 'mail.channel')], limit=1, context=context)
            followed_subtype_ids = mail_follower.browse(cr, uid, mail_follower_id, context=context).subtype_ids.ids
            # no super() call on purpose, no private links that could be quoted!
            channel = self.pool['mail.channel'].browse(cr, uid, mail.res_id, context=context)
            base_url = self.pool['ir.config_parameter'].get_param(cr, uid, 'web.base.url')
            vals = {
                'web_link': _('Web View'),
                'unsub': _('Unsubscribe'),
                'group_url': '%s/groups/%s' % (base_url, slug(channel)),
                'unsub_url': '%s/groups?unsubscribe' % (base_url,),
                'receive': _('Receive'),
                'recieve_urls': '%s | %s' % (_('One mail per thread'), _('All mails'))
            }
            footer = """_______________________________________________
                        %(web_link)s : %(group_url)s
                        %(unsub)s : %(unsub_url)s
                        %(receive)s : %(recieve_urls)s
                    """ % vals
            body = tools.append_content_to_html(mail.body, footer, container_tag='div')
            return body
        else:
            return super(MailMail, self).send_get_mail_body(cr, uid, ids, partner=partner, context=context)
