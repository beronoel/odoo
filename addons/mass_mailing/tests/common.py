# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import common


class TestMassMailingCommon(common.SavepointCase):

    @classmethod
    def setUpClass(cls):
        super(TestMassMailingCommon, cls).setUpClass()

        mass_mailing_list = cls.env['mail.mass_mailing.list']
        mass_mailing_contact = cls.env['mail.mass_mailing.contact']

        mass_mailing_list_2 = cls.env.ref('mass_mailing.mass_mail_list_2')

        cls.mass_mailing_list_01 = mass_mailing_list.create({
            'name': 'Employee Contact',
            })

        cls.mass_mailing_contact_04 = mass_mailing_contact.create({
            'name': 'Beverly Bridge',
            'email': 'bb@example.com',
            'list_id': cls.mass_mailing_list_01.id
            })

        cls.mass_mailing_contact_05 = mass_mailing_contact.create({
            'name': 'John Due',
            'email': 'john@example.com',
            'list_id': cls.mass_mailing_list_01.id
            })

        cls.merge_mailing_wizard = cls.env['mail.merge.mailing.list'].with_context({'active_model': 'mail.mass_mailing.list',
            'active_ids': [cls.mass_mailing_list_01.id, mass_mailing_list_2.id]}).create(
            {'mailing_list_ids': [(6, 0, [cls.mass_mailing_list_01.id, mass_mailing_list_2.id])], 'dst_massmail_list_id': cls.mass_mailing_list_01.id})
