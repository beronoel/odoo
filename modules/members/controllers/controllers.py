# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request
import members

class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        request_members = http.request.env['res.partner']
        module_members = members()

        return http.request.render('members.member_display', {'members': module_members.search_partner(request_members)})

