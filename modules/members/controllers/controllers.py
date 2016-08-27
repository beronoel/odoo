# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members/', auth='public')
    def access(self, **kw):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.registry

        partner_obj = pool['res.partner.partner_id_membership']
        partner_ids = partner_obj.search(cr, uid, [], context=context)
        print partner_ids

        return http.request.render('members.member_display', partner_ids)

    def display(self):


        http.request.render('members.test', "Hello, world")

