# -*- coding: utf-8 -*-
from urllib import urlencode

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
            follow_policy = {}
            query_string = {}
            mail_follower = self.pool['mail.followers']
            partner_uids = partner.user_ids.ids if partner else False
            if partner_uids:
                query_string['users'] = ','.join(str(partner_uid) for partner_uid in partner_uids)
            mail_follower_id = mail_follower.search(cr, uid, [('partner_id', '=', partner and partner.id or False), ('res_id', '=', mail.res_id), ('res_model', '=', 'mail.channel')], limit=1, context=context)
            mt_all_replies_id = self.pool['ir.model.data'].xmlid_to_res_id(cr, uid, 'mail.mt_all_replies')
            followed_subtype_ids = mail_follower.browse(cr, uid, mail_follower_id, context=context).subtype_ids.ids
            base_url = self.pool['ir.config_parameter'].get_param(cr, uid, 'web.base.url')
            if mt_all_replies_id in followed_subtype_ids:
                subtype_list = list(set(followed_subtype_ids) - set([mt_all_replies_id]))
                query_string['subtypes'] = ','.join(str(subtype) for subtype in subtype_list)
                follow_policy['one_per_thread'] = '<a href="%s/changesubscription/%d?%s">%s</a>' % (base_url, mail.res_id, urlencode(query_string), _('One mail per thread'))
                follow_policy['all'] = _('All mails')
            else:
                subtype_list = list(set(followed_subtype_ids) | set([mt_all_replies_id]))
                query_string['subtypes'] = ','.join(str(subtype) for subtype in subtype_list)
                follow_policy['one_per_thread'] = _('One mail per thread')
                follow_policy['all'] = '<a href="%s/changesubscription/%d?%s">%s</a>' % (base_url, mail.res_id, urlencode(query_string), _('All mails'))
            # no super() call on purpose, no private links that could be quoted!
            channel = self.pool['mail.channel'].browse(cr, uid, mail.res_id, context=context)
            vals = {
                'web_link': _('Web View'),
                'unsub': _('Unsubscribe'),
                'group_url': '%s/groups/%s' % (base_url, slug(channel)),
                'unsub_url': '%s/mail/unfollow?model=%s&res_id=%s' % (base_url, 'mail.channel', mail.res_id),
                'receive': _('Receive'),
                'recieve_urls': '%s | %s' % (follow_policy['one_per_thread'], follow_policy['all'])
            }
            footer = """_______________________________________________<br/>
                        %(web_link)s : %(group_url)s<br/>
                        %(unsub)s : %(unsub_url)s<br/>
                        %(receive)s : %(recieve_urls)s
                    """ % vals
            body = tools.append_content_to_html(mail.body, footer, plaintext=False, container_tag='div')
            return body
        else:
            return super(MailMail, self).send_get_mail_body(cr, uid, ids, partner=partner, context=context)
