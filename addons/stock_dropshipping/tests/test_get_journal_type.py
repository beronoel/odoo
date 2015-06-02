# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.tests.common import TransactionCase


class TestGetJournalType(TransactionCase):

    def test_so_and_po_on_delivery_gets_first_purchase_journal(self):
        self.so.order_policy = 'picking'
        self.so.action_button_confirm()

        po = self.so.procurement_group_id.procurement_ids.purchase_id
        self.assertTrue(po)
        po.invoice_method = 'picking'
        po.signal_workflow('purchase_confirm')

        picking = po.picking_ids
        self.assertEqual(1, len(picking))
        picking.action_done()

        wizard = self.Wizard.with_context({
            'active_id': picking.id,
            'active_ids': [picking.id],
        }).create({})
        self.assertEqual('in_invoice', wizard.invoice_type)

    def test_po_on_delivery_gets_purchase_journal(self):
        self.so.action_button_confirm()

        po = self.so.procurement_group_id.procurement_ids.purchase_id
        self.assertTrue(po)
        po.invoice_method = 'picking'
        po.signal_workflow('purchase_confirm')

        picking = po.picking_ids
        self.assertEqual(1, len(picking))
        picking.action_done()

        wizard = self.Wizard.with_context({
            'active_id': picking.id,
            'active_ids': [picking.id],
        }).create({})
        self.assertEqual('in_invoice', wizard.invoice_type)

    def test_so_on_delivery_gets_sale_journal(self):
        self.so.order_policy = 'picking'
        self.so.action_button_confirm()
        po = self.so.procurement_group_id.procurement_ids.purchase_id
        self.assertTrue(po)
        po.signal_workflow('purchase_confirm')

        picking = po.picking_ids
        self.assertEqual(1, len(picking))
        picking.action_done()

        wizard = self.Wizard.with_context({
            'active_id': picking.id,
            'active_ids': [picking.id],
        }).create({})
        self.assertEqual('out_invoice', wizard.invoice_type)

    def setUp(self):
        super(TestGetJournalType, self).setUp()
        self.Wizard = self.env['stock.invoice.onshipping']

        customer = self.env.ref('base.res_partner_3')
        product = self.env.ref('product.product_product_36')
        dropship_route = self.env.ref('stock_dropshipping.route_drop_shipping')

        self.so = self.env['sale.order'].create({
            'partner_id': customer.id,
        })
        self.sol = self.env['sale.order.line'].create({
            'name': '/',
            'order_id': self.so.id,
            'product_id': product.id,
            'route_id': dropship_route.id,
        })
