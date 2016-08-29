# -*- coding: utf-8 -*-
from openerp import http

class Members(http.Controller):
    @http.route('/members/members/', auth='public')
    def access(self, **kw):
        record_members = http.request.env['res.partner'].sudo()

        result_record = record_members.search([('partner_id_membership', '=', '29334011400439')])

        return http.request.render('members.member_display', {'members': result_record})

