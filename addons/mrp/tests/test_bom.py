# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.mrp.tests.common import TestMrpCommon


class TestBoM(TestMrpCommon):

    def test_basic(self):
        self.assertEqual(self.production_1.state, 'confirmed')

        # produce product
        produce_wizard = self.env['mrp.product.produce'].with_context({
            'active_id': self.production_1.id,
            'active_ids': [self.production_1.id],
        }).create({
            'product_qty': 1.0,
        })
        # produce_wizard.on_change_qty()
        produce_wizard.do_produce()

        # check production
        # self.assertEqual(production.state, 'done')

    def test_explode(self):
        res = self.bom_1.explode_new(3)
        # print '--------'
        # print res

    def test_explode_from_order(self):
        # reset quantities
        self.env['stock.change.product.qty'].create({
            'product_id': self.product_1.id,
            'new_quantity': 0.0,
            'location_id': self.warehouse_1.lot_stock_id.id,
        }).change_product_qty()

        (self.product_2 | self.product_4).write({
            'tracking': 'lot',
        })
        # assign consume material
        self.production_1.action_assign()
        self.assertEqual(self.production_1.availability, 'waiting')

        # check consume materials of manufacturing order
        self.assertEqual(len(self.production_1.move_raw_ids), 3)
        # for move in self.production_1.move_raw_ids:
        #     print move.name, move.state, move.product_id, move.product_qty, move.product_uom_qty, move.unit_factor
        product_2_consume_moves = self.production_1.move_raw_ids.filtered(lambda x: x.product_id == self.product_2)
        product_4_consume_moves = self.production_1.move_raw_ids.filtered(lambda x: x.product_id == self.product_4)
        product_5_consume_moves = self.production_1.move_raw_ids.filtered(lambda x: x.product_id == self.product_5)
        self.assertEqual(product_2_consume_moves.product_uom_qty, 2.0)
        self.assertEqual(product_4_consume_moves.product_uom_qty, 6.0)
        self.assertEqual(product_5_consume_moves.product_uom_qty, 3.0)

        # create required lots
        lot_product_2 = self.env['stock.production.lot'].create({'product_id': self.product_2.id})
        lot_product_4 = self.env['stock.production.lot'].create({'product_id': self.product_4.id})

        # refuel stock
        inventory = self.env['stock.inventory'].create({
            'name': 'Inventory For Product C',
            'filter': 'partial',
            'line_ids': [(0, 0, {
                'product_id': self.product_2.id,
                'product_uom_id': self.product_2.uom_id.id,
                'product_qty': 30,
                'prod_lot_id': lot_product_2.id,
                'location_id': self.ref('stock.stock_location_14')
            }), (0, 0, {
                'product_id': self.product_4.id,
                'product_uom_id': self.product_5.uom_id.id,
                'product_qty': 60,
                'prod_lot_id': lot_product_4.id,
                'location_id': self.ref('stock.stock_location_14')
            }), (0, 0, {
                'product_id': self.product_5.id,
                'product_uom_id': self.product_5.uom_id.id,
                'product_qty': 60,
                'location_id': self.ref('stock.stock_location_14')
            })]
        })
        inventory.prepare_inventory()
        inventory.action_done()

        # re-assign consume material
        self.production_1.action_assign()

        # Check production order status after assign.
        self.assertEqual(self.production_1.availability, 'assigned')
        # Plan production order.
        self.production_1.button_plan()

        # check workorders

        workorders = self.production_1.workorder_ids
        # for workorder in workorders:
        #     print workorder.name, workorder.product_id, workorder.qty_producing

        # first machine (machine A)
        # self.assertEqual(workorders[0].duration, 40)
        workorders[0].button_start()
        finished_lot = self.env['stock.production.lot'].create({'product_id': self.production_1.product_id.id})
        workorders[0].write({'final_lot_id': finished_lot.id, 'qty_producing': 48})

        product_d_move_lot = workorders[0].active_move_lot_ids.filtered(lambda x: x.product_id == self.product_2)
        product_d_move_lot.write({'lot_id': lot_product_2.id, 'quantity_done': 2})
        workorders[0].record_production()

        # Check machine B process....
        # self.assertEqual(workorders[1].duration, 20, "Workorder duration does not match.")
        workorders[1].button_start()
        product_f_move_lot = workorders[1].active_move_lot_ids.filtered(lambda x: x.product_id == self.product_5)
        product_f_move_lot.write({'lot_id': lot_product_4.id, 'quantity_done': 6})
        workorders[1].record_production()
        self.production_1.button_mark_done()
