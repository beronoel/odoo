# -*- coding: utf-8 -*-
from openerp import http


class Members(http.Controller):
    @http.route('/members/', auth='public')
    def index(self, **kw):
        return "Hello, world"

    @http.route('/members/objects/', auth='public')
    def list(self, **kw):
        return http.request.render('members.listing', {
            'root': '/members',
            'objects': http.request.env['members.members'].search([]),
        })

    @http.route('/members/objects/<model("members.members"):obj>/', auth='public')
    def object(self, obj, **kw):
        return http.request.render('members.object', {
            'object': obj
        })
