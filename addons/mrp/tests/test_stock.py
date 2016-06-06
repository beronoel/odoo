# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import common


class TestWarehouse(common.TestMrpCommon):

    def test_manufacturing_route(self):
        warehouse_1_stock_manager = self.warehouse_1.sudo(self.user_stock_manager)
        manu_rule = self.env['procurement.rule'].search([
            ('action', '=', 'manufacture'),
            ('warehouse_id', '=', self.warehouse_1.id)])
        self.assertEqual(self.warehouse_1.manufacture_pull_id, manu_rule)
        manu_route = manu_rule.route_id
        self.assertIn(manu_route, warehouse_1_stock_manager._get_all_routes())
        warehouse_1_stock_manager.write({
            'manufacture_to_resupply': False
        })
        self.assertFalse(self.warehouse_1.manufacture_pull_id)
        self.assertFalse(self.warehouse_1.manu_type_id.active)
        self.assertNotIn(manu_route, warehouse_1_stock_manager._get_all_routes())
        warehouse_1_stock_manager.write({
            'manufacture_to_resupply': True
        })
        manu_rule = self.env['procurement.rule'].search([
            ('action', '=', 'manufacture'),
            ('warehouse_id', '=', self.warehouse_1.id)])
        self.assertEqual(self.warehouse_1.manufacture_pull_id, manu_rule)
        self.assertTrue(self.warehouse_1.manu_type_id.active)
        self.assertIn(manu_route, warehouse_1_stock_manager._get_all_routes())
