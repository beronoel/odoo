# -*- coding: utf-8 -*-

from openerp import models, fields, api


class members(models.Model):
    _inherits = 'res.partner'
    _name = 'members.members'

    """
    @api.depends('member_UID')
    def _search_partner(self):
        # Return info of membership
        if self.ids:
            ids_to_search = []
            for partner in self:
                if partner.associate_member:
                    ids_to_search.append(partner.associate_member.partner_id_membership)
                else:
                    ids_to_search.append(partner.partner_id_membership)
            self.env.cr.execute('''
                            SELECT
                                p.id as id,
                                MIN(m.date_from) as membership_start,
                                MAX(m.date_to) as membership_stop,
                                MIN(CASE WHEN m.date_cancel is not null THEN 1 END) as membership_cancel
                            FROM
                                res_partner p
                            LEFT JOIN
                                membership_membership_line m
                                ON (m.partner = p.id)
                            WHERE
                                p.id IN %s
                            GROUP BY
                                p.id''', (tuple(ids_to_search),))
            for record in self.env.cr.dictfetchall():
                partner = self.browse(record.pop('id')).update(record)
    """
