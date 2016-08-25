# -*- coding: utf-8 -*-
from openerp import http


class Members(http.Controller):
    @http.route('/members/members/', auth='public', website=True)
    def index(self, **kw):
        return http.request.render('academy.index', "Hello, world")

    @http.route('/members/members/objects/', auth='public', website=True)
    def list(self, **kw):
        return http.request.render('members.listing', {
            'root': '/members',
            'objects': http.request.env['members.members'].search([]),
        })

    @http.route('/members/members/objects/<model("members.members"):obj>/', auth='public', website=True)
    def object(self, obj, **kw):
        return http.request.render('members.object', {
            'object': obj
        })
