# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request


class Members(http.Controller):
    @http.route('/members', type='http', auth='public', website=True)
    def access(self, **kw):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.registry

        partner_obj = pool['res.partner.partner_id_membership']
        partner_ids = partner_obj.search(cr, uid, [], context=context)
        print partner_ids


        return http.request.render('members.display', partner_obj)

    def display(self):


        http.request.render('members.test', "Hello, world")

