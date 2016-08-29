# -*- coding: utf-8 -*-
from openerp import http
from wtforms import Form, StringField

class Members(http.Controller):
    @http.route('/members/members/', website=True)
    def create(self, **post_data):
        form = SearchForm(http.request.httprequest.form)
        if http.request.httprequest.method == 'POST':
            unique_id = form.unique_id.data  # '29334011400439'
            print unique_id

            record_members = http.request.env['res.partner'].sudo()
            result_record = record_members.search([('partner_id_membership', '=', str(unique_id))])

            return http.request.render('members.member_display', {'members': result_record})

        return http.request.render('members.search_partner', {'form': form})

class SearchForm(Form):
    unique_id = StringField('unique_id')

