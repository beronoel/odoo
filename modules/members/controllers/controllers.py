# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        #Members = http.request.env['res.partner']
        Members = http.request.env['members.members']

        return http.request.render('members.member_display', {'members': Members.search([])})

