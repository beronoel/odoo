# -*- coding: utf-8 -*-
from openerp import http
from openerp.http import request
from openerp import SUPERUSER_ID

class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        record_members = http.request.env['res.partner'].sudo()

        result_record = record_members.search([('id', '=', '1')])
        #result_record = record_members.search(cr, uid, [('id', '=', '1')], context=context)
        print result_record

        return http.request.render('members.member_display', {'members': result_record})

