# -*- coding: utf-8 -*-
from openerp import http


class Members(http.Controller):
    @http.route('/members/members/', auth='public', website=True)
    def index(self, **kw):
        return http.request.render('members.index', "Hello, world")

