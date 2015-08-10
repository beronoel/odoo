import base64
from operator import itemgetter
import psycopg2

import openerp
from openerp import SUPERUSER_ID
from openerp import http, _
from openerp.exceptions import AccessError
from openerp.http import request
from openerp.tools import plaintext2html
from openerp.addons.web.controllers.main import content_disposition
import mimetypes


class MailController(http.Controller):
    _cp_path = '/mail'

    @http.route('/mail/download_attachment', type='http', auth='user')
    def download_attachment(self, model, id, method, attachment_id, **kw):
        # FIXME use /web/binary/saveas directly
        Model = request.registry.get(model)
        res = getattr(Model, method)(request.cr, request.uid, int(id), int(attachment_id))
        if res:
            filecontent = base64.b64decode(res.get('base64'))
            filename = res.get('filename')
            content_type = mimetypes.guess_type(filename)
            if filecontent and filename:
                return request.make_response(
                    filecontent,
                    headers=[('Content-Type', content_type[0] or 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(filename))])
        return request.not_found()

    @http.route('/mail/receive', type='json', auth='none')
    def receive(self, req):
        """ End-point to receive mail from an external SMTP server. """
        dbs = req.jsonrequest.get('databases')
        for db in dbs:
            message = dbs[db].decode('base64')
            try:
                registry = openerp.registry(db)
                with registry.cursor() as cr:
                    mail_thread = registry['mail.thread']
                    mail_thread.message_process(cr, SUPERUSER_ID, None, message)
            except psycopg2.Error:
                pass
        return True

    @http.route('/mail/read_followers', type='json', auth='user')
    def read_followers(self, follower_ids):
        result = []
        is_editable = request.env.user.has_group('base.group_no_one')
        for follower in request.env['res.partner'].browse(follower_ids):
            result.append({
                'id': follower.id,
                'name': follower.name,
                'is_editable': is_editable,
                'is_uid': request.env.user.partner_id == follower,
            })
        return result

    @http.route('/mail/read_subscription_data', type='json', auth='user')
    def read_subscription_data(self, res_model, res_id):
        """ Computes:
            - message_subtype_data: data about document subtypes: which are
                available, which are followed if any """
        # find the document followers, update the data
        followers = request.env['mail.followers'].search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('res_id', '=', res_id),
            ('res_model', '=', res_model),
        ])

        # find current model subtypes, add them to a dictionary
        # For mail.channle model, we want to display 'Discussion' subtype as 'Discussion Initated'
        mt_discussion_id = request.env.ref('mail.mt_comment', raise_if_not_found=False).id
        subtypes = request.env['mail.message.subtype'].search(['&', ('hidden', '=', False), '|', ('res_model', '=', res_model), ('res_model', '=', False)])
        subtypes_list = [{
            'name': _("Discussion Initiated") if res_model == "mail.channel" and subtype.id == mt_discussion_id else subtype.name,
            'res_model': subtype.res_model,
            'sequence': subtype.sequence,
            'default': subtype.default,
            'internal': subtype.internal,
            'followed': subtype.id in followers.mapped('subtype_ids').ids,
            'parent_model': subtype.parent_id and subtype.parent_id.res_model or False,
            'id': subtype.id
        } for subtype in subtypes]
        subtypes_list = sorted(subtypes_list, key=itemgetter('parent_model', 'res_model', 'internal', 'sequence'))

        return subtypes_list

    @http.route('/mail/follow', type='http', auth='user')
    def message_subscribe(self, model, res_id):
        document = request.env[model].browse(int(res_id))
        document.message_subscribe_users()
        base_url = request.env['ir.config_parameter'].get_param('web.base.url')
        vals = {'user': request.env.user.name, 'base_url': base_url, 'mail_subscribe': True, 'doc_name': document.name_get()[0][1]}
        return request.render('mail.mail_subscriptionchange', vals)

    @http.route('/mail/unfollow', type='http', auth='user')
    def message_unsubscribe(self, model, res_id):
        document = request.env[model].browse(int(res_id))
        document.message_unsubscribe_users()
        base_url = request.env['ir.config_parameter'].get_param('web.base.url')
        vals = {'user': request.env.user.name, 'base_url': base_url, 'mail_unsubscribe': True, 'doc_name': document.name_get()[0][1]}
        return request.render('mail.mail_subscriptionchange', vals)

    @http.route('/mail/execute', type='http', auth='user')
    def message_execute(self, model, res_id, action, **kwargs):
        vals = {}
        vals['base_url'] = request.env['ir.config_parameter'].get_param('web.base.url')
        try:
            if hasattr(request.env[model], action):
                getattr(request.env[model].browse(int(res_id)), action)()
            vals['success_msg'] = _('Action is perfomed successfully!')
        except AccessError as e:
            vals['access_error'] = plaintext2html(e.name)
        return request.render('mail.mail_actions', vals)
