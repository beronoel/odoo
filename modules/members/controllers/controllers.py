# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
        Members = http.request.env['res.partner']

        return http.request.render('members.member_display', {'members': Members.search([('name', '=', 'Benjamin De Leener')])})

