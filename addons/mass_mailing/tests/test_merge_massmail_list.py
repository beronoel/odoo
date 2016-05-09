# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from .common import TestMassMailingCommon


class TestMergeMassmailList(TestMassMailingCommon):

    def test_00_merge_massmail_list(self):
        """Merge massmail list without remove duplicate recipients """

        # Select mass mailing list from mailing list.
        self.merge_mailing_wizard.write({'remove_duplicate': False})
        dst_massmail_list = self.merge_mailing_wizard.dst_massmail_list_id
        mass_mail_lists = self.merge_mailing_wizard.mailing_list_ids.filtered(lambda m: m.id != dst_massmail_list.id)

        # Merge mass mailing list without remove duplicate.
        self.merge_mailing_wizard.action_massmail_merge()

        #Check recipients of Destination mailing list after merge with recipients of mailing lists, it should be 4.
        self.assertEqual(len(dst_massmail_list.recipient_ids), 4, 'Recipients of destination mailing list should be 4 after merged with duplicate massmailing lists.')
        dst_massmail_recipients_emails = dst_massmail_list.recipient_ids.mapped('email')

        self.assertNotEqual(len(dst_massmail_recipients_emails), len(set(dst_massmail_recipients_emails)), 'Recipients of destination Mailing list should be duplicate.')

    def test_01_merge_massmail_list_remove_duplicate(self):
        """Merge massmail list with remove duplicate recipients"""

        # Select mass mailing list from mailing list.
        self.merge_mailing_wizard.write({'remove_duplicate': True})
        dst_massmail_list = self.merge_mailing_wizard.dst_massmail_list_id
        mass_mail_lists = self.merge_mailing_wizard.mailing_list_ids.filtered(lambda m: m.id != dst_massmail_list.id)

        # Merge mass mailing list with remove duplicate.
        self.merge_mailing_wizard.action_massmail_merge()

        #Check recipients of Destination mailing list after merge with recipients of mailing lists, it should be 3.
        self.assertEqual(len(dst_massmail_list.recipient_ids), 3)
        dst_massmail_recipients_emails = dst_massmail_list.recipient_ids.mapped('email')

        self.assertEqual(len(dst_massmail_recipients_emails), len(set(dst_massmail_recipients_emails)), 'Recipients of destination Mailing list should not be duplicate.')
