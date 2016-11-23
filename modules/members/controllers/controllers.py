# -*- coding: utf-8 -*-
from openerp import http
from wtforms import Form, StringField
from odoo import api, models, fields, _


class Members(http.Controller):
    @http.route('/members/', auth='public', website=True)
    def create(self, **post_data):
        form = SearchForm(http.request.httprequest.form)
        if http.request.httprequest.method == 'POST':
            unique_id = form.unique_id.data
            form.unique_id.data = ''

            record_members = http.request.env['res.partner'].sudo()
            result_record = record_members.search([('partner_id_membership', '=', str(unique_id))])

            for partner in result_record:
                p = record_members.browse(partner.id)

                record_checkin = http.request.env['members.checkin'].sudo()
                if p.is_in:
                    # modify the latest entry of the member in the check-in history
                    result_record_checkin = record_checkin.search([('partner.partner_id_membership', '=', p.partner_id_membership)])
                    latest_record_checkin = record_checkin.browse(result_record_checkin[-1].id)
                    latest_record_checkin.write({'date_check_out': fields.DateTime.now()})
                else:
                    # add a new entry to check-in history
                    record_checkin.create({'partner': partner, 'date_check_in': fields.Datetime.now(), 'date_check_out': fields.DateTime.now()})

                p.write({'is_in': not partner.is_in})
                for qualification in partner.qualification_lines:
                    if qualification.valid: qualification.valid = 'Oui'
                    else: qualification.valid = 'Non'

            return http.request.render('members.search_partner', {'form': form, 'members': result_record})

        return http.request.render('members.search_partner', {'form': form, 'members': []})

class SearchForm(Form):
    unique_id = StringField('Unique Identification Number')

