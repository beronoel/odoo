# -*- coding: utf-8 -*-
from openerp import http
from wtforms import Form, StringField

class Members(http.Controller):
    @http.route('/members/members/', website=True)
    def create(self, **post_data):
        form = SearchForm()
        return http.request.render('members.search_partner', {'form': form})

    @http.route('/members/search/', type='http', auth='public', methods=['POST'])
    def search(self, **kw):
        form = SearchForm(http.request.httprequest.form)
        unique_id = form.unique_id.data  # '29334011400439'

        record_members = http.request.env['res.partner'].sudo()
        result_record = record_members.search([('partner_id_membership', '=', unique_id)])

        return http.request.render('members.member_display', {'members': result_record})

class SearchForm(Form):
    unique_id = StringField('unique_id')

