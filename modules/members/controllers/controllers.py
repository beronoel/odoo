# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        Teachers = http.request.env['academy.teachers']

        return http.request.render('members.member_display', {'teachers': Teachers.search([])})

