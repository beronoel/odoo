# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        partner_ids = 'test'

        print partner_ids

        return http.request.render('members.member_display', partner_ids)

