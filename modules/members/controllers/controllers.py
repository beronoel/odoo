# -*- coding: utf-8 -*-
from openerp import http
from wtforms import Form, StringField

class Members(http.Controller):
    @http.route('/members/', auth='public', website=True)
    def create(self, **post_data):
        form = SearchForm(http.request.httprequest.form)
        if http.request.httprequest.method == 'POST':
            unique_id = form.unique_id.data  # '29334011400439'

            record_members = http.request.env['res.partner'].sudo()
            result_record = record_members.search([('partner_id_membership', '=', str(unique_id))])

            for partner in result_record:
                p = record_members.browse(partner.id)
                p.write({'is_in': True})

            return http.request.render('members.search_partner', {'form': form, 'members': result_record})

        return http.request.render('members.search_partner', {'form': form, 'members': []})

class SearchForm(Form):
    unique_id = StringField('Unique Identification Number')

