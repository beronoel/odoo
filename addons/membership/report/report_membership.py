# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools
from odoo.addons.membership.models import membership


class ReportCheckin(models.Model):
    _name = 'report.checkin'
    _description = __doc__
    _auto = False

    date_check_in = fields.Datetime('Date Check-In', readonly=True)
    date_check_out = fields.Datetime('Date Check-Out', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Member', readonly=True)
    associate_member_id = fields.Many2one('res.partner', 'Associate Member', readonly=True)
    membership_id = fields.Many2one('product.product', 'Membership Product', readonly=True)
    membership_state = fields.Selection(membership.STATE, 'Current Membership State', readonly=True)
    quantity_checkin = fields.Integer(readonly=True)
    quantity_members = fields.Integer(readonly=True)

    def init(self, cr):
        '''Create the view'''
        tools.drop_view_if_exists(cr, 'report_checkin')
        cr.execute("""
        CREATE OR REPLACE VIEW report_checkin AS (
        SELECT
        MIN(id) AS id,
        partner_id,
        count(check_id) as quantity_checkin,
        count(membership_id) as quantity_members,
        membership_state,
        associate_member_id,
        membership_id,
        date_check_in,
        date_check_out
        FROM
        (SELECT
            MIN(p.id) AS id,
            p.id AS partner_id,
            p.membership_state AS membership_state,
            p.associate_member AS associate_member_id,
            ml.membership_id AS membership_id,
            mc.id AS check_id,
            mc.date_check_in AS date_check_in,
            mc.date_check_out AS date_check_out
            FROM res_partner p
            LEFT JOIN membership_membership_line ml ON (ml.partner = p.id)
            LEFT JOIN members_checkin mc ON (mc.partner = p.id)
            GROUP BY
              p.id,
              p.user_id,
              p.membership_state,
              p.associate_member,
              p.membership_start,
              ml.membership_id,
              ml.state,
              ml.id,
              mc.id,
              mc.date_check_in,
              mc.date_check_out
        ) AS foo
        GROUP BY
            partner_id,
            membership_id,
            membership_state,
            associate_member_id,
            check_id,
            date_check_in,
            date_check_out
        )""")


class ReportMembership(models.Model):
    '''Membership Analysis'''

    _name = 'report.membership'
    _description = __doc__
    _auto = False
    _rec_name = 'start_date'
    start_date = fields.Date(readonly=True)
    join_date = fields.Date('Join Date', readonly=True)
    date_to = fields.Date('End Date', readonly=True, help="End membership date")
    num_waiting = fields.Integer('# Waiting', readonly=True)
    num_invoiced = fields.Integer('# Invoiced', readonly=True)
    num_paid = fields.Integer('# Paid', readonly=True)
    tot_pending = fields.Float('Pending Amount', digits=0, readonly=True)
    tot_earned = fields.Float('Earned Amount', digits=0, readonly=True)
    partner_id = fields.Many2one('res.partner', 'Member', readonly=True)
    associate_member_id = fields.Many2one('res.partner', 'Associate Member', readonly=True)
    membership_id = fields.Many2one('product.product', 'Membership Product', readonly=True)
    membership_state = fields.Selection(membership.STATE, 'Current Membership State', readonly=True)
    user_id = fields.Many2one('res.users', 'Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    quantity = fields.Integer(readonly=True)

    def init(self, cr):
        '''Create the view'''
        tools.drop_view_if_exists(cr, 'report_membership')
        cr.execute("""
        CREATE OR REPLACE VIEW report_membership AS (
        SELECT
        MIN(id) AS id,
        partner_id,
        count(membership_id) as quantity,
        user_id,
        membership_state,
        associate_member_id,
        membership_amount,
        date_to,
        start_date,
        join_date,
        COUNT(num_waiting) AS num_waiting,
        COUNT(num_invoiced) AS num_invoiced,
        COUNT(num_paid) AS num_paid,
        SUM(tot_pending) AS tot_pending,
        SUM(tot_earned) AS tot_earned,
        membership_id,
        company_id
        FROM
        (SELECT
            MIN(p.id) AS id,
            p.id AS partner_id,
            p.user_id AS user_id,
            p.membership_state AS membership_state,
            p.associate_member AS associate_member_id,
            p.membership_amount AS membership_amount,
            p.membership_stop AS date_to,
            p.membership_start AS start_date,
            CASE WHEN ml.state = 'waiting'  THEN ml.id END AS num_waiting,
            CASE WHEN ml.state = 'invoiced' THEN ml.id END AS num_invoiced,
            CASE WHEN ml.state = 'paid'     THEN ml.id END AS num_paid,
            CASE WHEN ml.state IN ('waiting', 'invoiced') THEN SUM(il.price_subtotal) ELSE 0 END AS tot_pending,
            CASE WHEN ml.state = 'paid' OR p.membership_state = 'old' THEN SUM(il.price_subtotal) ELSE 0 END AS tot_earned,
            ml.membership_id AS membership_id,
            ml.date AS join_date,
            p.company_id AS company_id
            FROM res_partner p
            LEFT JOIN membership_membership_line ml ON (ml.partner = p.id)
            LEFT JOIN account_invoice_line il ON (ml.account_invoice_line = il.id)
            LEFT JOIN account_invoice ai ON (il.invoice_id = ai.id)
            WHERE p.membership_state != 'none' and p.active = 'true'
            GROUP BY
              p.id,
              p.user_id,
              p.membership_state,
              p.associate_member,
              p.membership_amount,
              p.membership_start,
              ml.membership_id,
              p.company_id,
              ml.state,
              ml.id
        ) AS foo
        GROUP BY
            start_date,
            date_to,
            join_date,
            partner_id,
            user_id,
            membership_id,
            company_id,
            membership_state,
            associate_member_id,
            membership_amount
        )""")
