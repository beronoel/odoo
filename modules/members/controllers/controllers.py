# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):

        return http.request.render('members.member_display', {'teachers': ["Diana Padilla", "Jody Caroll", "Lester Vaughn"]})

