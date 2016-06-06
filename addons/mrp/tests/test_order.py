# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta

from odoo.fields import Datetime as Dt
from odoo.addons.mrp.tests.common import TestMrpCommon


class TestMrpOrder(TestMrpCommon):

    def test_access_rights_manager(self):
        man_order = self.env['mrp.production'].sudo(self.user_mrp_manager).create({
            'name': 'Stick-0',
            'product_id': self.product_4.id,
            'product_uom_id': self.product_4.uom_id.id,
            'product_qty': 5.0,
            'bom_id': self.bom_1.id,
            'location_src_id': self.location_1.id,
            'location_dest_id': self.warehouse_1.wh_output_stock_loc_id.id,
        })
        man_order.action_cancel()
        self.assertEqual(man_order.state, 'cancel')
        man_order.unlink()

    def test_access_rights_user(self):
        man_order = self.env['mrp.production'].sudo(self.user_mrp_user).create({
            'name': 'Stick-0',
            'product_id': self.product_4.id,
            'product_uom_id': self.product_4.uom_id.id,
            'product_qty': 5.0,
            'bom_id': self.bom_1.id,
            'location_src_id': self.location_1.id,
            'location_dest_id': self.warehouse_1.wh_output_stock_loc_id.id,
        })
        man_order.action_cancel()
        self.assertEqual(man_order.state, 'cancel')
        man_order.unlink()

    def test_basic(self):
        """ Basic order test: no routing (thus no workorders), no lot """
        inventory = self.env['stock.inventory'].create({
            'name': 'Initial inventory',
            'filter': 'partial',
            'line_ids': [(0, 0, {
                'product_id': self.product_1.id,
                'product_uom_id': self.product_1.uom_id.id,
                'product_qty': 500,
                'location_id': self.warehouse_1.lot_stock_id.id
            }), (0, 0, {
                'product_id': self.product_2.id,
                'product_uom_id': self.product_2.uom_id.id,
                'product_qty': 500,
                'location_id': self.warehouse_1.lot_stock_id.id
            })]
        })
        inventory.action_done()

        test_date_planned = datetime.now() - timedelta(days=1)
        test_quantity = 2.0
        self.bom_1.routing_id = False
        man_order = self.env['mrp.production'].sudo(self.user_mrp_user).create({
            'name': 'Stick-0',
            'product_id': self.product_4.id,
            'product_uom_id': self.product_4.uom_id.id,
            'product_qty': test_quantity,
            'bom_id': self.bom_1.id,
            'date_planned': test_date_planned,
            'location_src_id': self.location_1.id,
            'location_dest_id': self.warehouse_1.wh_output_stock_loc_id.id,
        })
        self.assertEqual(man_order.state, 'confirmed')

        # check production move
        production_move = man_order.move_finished_ids
        self.assertEqual(production_move.date, Dt.to_string(test_date_planned))
        self.assertEqual(production_move.product_id, self.product_4)
        self.assertEqual(production_move.product_uom, man_order.product_uom_id)
        self.assertEqual(production_move.product_qty, man_order.product_qty)
        self.assertEqual(production_move.location_id, self.product_4.property_stock_production)
        self.assertEqual(production_move.location_dest_id, man_order.location_dest_id)

        # check consumption moves
        for move in man_order.move_raw_ids:
            self.assertEqual(move.date, Dt.to_string(test_date_planned))
        first_move = man_order.move_raw_ids.filtered(lambda move: move.product_id == self.product_2)
        self.assertEqual(first_move.product_qty, test_quantity / self.bom_1.product_qty * self.product_4.uom_id.factor_inv * 2)
        first_move = man_order.move_raw_ids.filtered(lambda move: move.product_id == self.product_1)
        self.assertEqual(first_move.product_qty, test_quantity / self.bom_1.product_qty * self.product_4.uom_id.factor_inv * 4)

        # waste some material, create a scrap
        # scrap = self.env['stock.scrap'].with_context(
        #     active_model='mrp.production', active_id=man_order.id
        # ).create({})
        # scrap = self.env['stock.scrap'].create({
        #     'production_id': man_order.id,
        #     'product_id': first_move.product_id.id,
        #     'product_uom_id': first_move.product_uom.id,
        #     'scrap_qty': 5.0,
        # })
        # check created scrap


        # procurements = self.env['procurement.order'].search([('move_dest_id', 'in', man_order.move_raw_ids.ids)])
        # print procurements
        # procurements = self.env['procurement.order'].search([('production_id', '=', man_order.id)])
        # print procurements
        # for proc in self.env['procurement.order'].browse(procurements):
        #     date_planned = self.mrp_production_test1.date_planned
        #     if proc.product_id.type not in ('product', 'consu'):
        #         continue
        #     if proc.product_id.id == order_line.product_id.id:
        #         self.assertEqual(proc.date_planned, date_planned, "Planned date does not correspond")
        #       # procurement state should be `confirmed` at this stage, except if procurement_jit is installed, in which
        #       # case it could already be in `running` or `exception` state (not enough stock)
        #         expected_states = ('confirmed', 'running', 'exception')
        #         self.assertEqual(proc.state in expected_states, 'Procurement state is `%s` for %s, expected one of %s' % (proc.state, proc.product_id.name, expected_states))

        # Change production quantity
        qty_wizard = self.env['change.production.qty'].create({
            'mo_id': man_order.id,
            'product_qty': 3.0,
        })
        # qty_wizard.change_prod_qty()

        # # I check qty after changed in production order.
        # #self.assertEqual(self.mrp_production_test1.product_qty, 3, "Qty is not changed in order.")
        # move = self.mrp_production_test1.move_finished_ids[0]
        # self.assertEqual(move.product_qty, self.mrp_production_test1.product_qty, "Qty is not changed in move line.")

        # # I run scheduler.
        # self.env['procurement.order'].run_scheduler()

        # # The production order is Waiting Goods, will force production which should set consume lines as available
        # self.mrp_production_test1.button_plan()
        # # I check that production order in ready state after forcing production.

        # #self.assertEqual(self.mrp_production_test1.availability, 'assigned', 'Production order availability should be set as available')

        # produce product
        produce_wizard = self.env['mrp.product.produce'].sudo(self.user_mrp_user).with_context({
            'active_id': man_order.id,
            'active_ids': [man_order.id],
        }).create({
            'product_qty': 1.0,
        })
        produce_wizard.do_produce()

        # man_order.button_mark_done()
        man_order.button_mark_done()
        self.assertEqual(man_order.state, 'done')

    def test_explode_from_order(self):
        #
        # bom3 produces 2 Dozen of Doors (p6), aka 24
        # To produce 24 Units of Doors (p6)
        # - 2 Units of Tools (p5) -> need 4
        # - 8 Dozen of Sticks (p4) -> need 16
        # - 12 Units of Wood (p2) -> need 24
        # bom2 produces 1 Unit of Sticks (p4)
        # To produce 1 Unit of Sticks (p4)
        # - 2 Dozen of Sticks (p4) -> need 8
        # - 3 Dozen of Stones (p3) -> need 12
        man_order = self.env['mrp.production'].create({
            'name': 'MO-Test',
            'product_id': self.product_6.id,
            'product_uom_id': self.product_6.uom_id.id,
            'product_qty': 48,
            'bom_id': self.bom_3.id,
        })

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
        man_order.action_assign()
        self.assertEqual(man_order.availability, 'waiting')

        # check consume materials of manufacturing order
        # for move in man_order.move_raw_ids:
        #     print move.name, move.state, move.product_id, move.product_id.name, move.product_qty, move.product_uom_qty, move.unit_factor
        self.assertEqual(len(man_order.move_raw_ids), 4)
        product_2_consume_moves = man_order.move_raw_ids.filtered(lambda x: x.product_id == self.product_2)
        product_3_consume_moves = man_order.move_raw_ids.filtered(lambda x: x.product_id == self.product_3)
        product_4_consume_moves = man_order.move_raw_ids.filtered(lambda x: x.product_id == self.product_4)
        product_5_consume_moves = man_order.move_raw_ids.filtered(lambda x: x.product_id == self.product_5)
        self.assertEqual(product_2_consume_moves.product_uom_qty, 24.0)
        self.assertEqual(product_3_consume_moves.product_uom_qty, 12.0)
        self.assertEqual(len(product_4_consume_moves), 2)
        for product_4_move in product_4_consume_moves:
            self.assertIn(product_4_move.product_uom_qty, [8.0, 16.0])
        self.assertFalse(product_5_consume_moves)

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
                'product_id': self.product_3.id,
                'product_uom_id': self.product_3.uom_id.id,
                'product_qty': 60,
                'location_id': self.ref('stock.stock_location_14')
            }), (0, 0, {
                'product_id': self.product_4.id,
                'product_uom_id': self.product_4.uom_id.id,
                'product_qty': 60,
                'prod_lot_id': lot_product_4.id,
                'location_id': self.ref('stock.stock_location_14')
            })]
        })
        inventory.prepare_inventory()
        inventory.action_done()

        # re-assign consume material
        man_order.action_assign()

        # Check production order status after assign.
        self.assertEqual(man_order.availability, 'assigned')
        # Plan production order.
        man_order.button_plan()

        # check workorders
        # - main bom: Door: 2 operations
        #   operation 1: Cutting
        #   operation 2: Welding, waiting for the previous one
        # - kit bom: Stone Tool: 1 operation
        #   operation 1: Gift Wrapping
        workorders = man_order.workorder_ids
        kit_wo = man_order.workorder_ids.filtered(lambda wo: wo.operation_id == self.operation_1)
        door_wo_1 = man_order.workorder_ids.filtered(lambda wo: wo.operation_id == self.operation_2)
        door_wo_2 = man_order.workorder_ids.filtered(lambda wo: wo.operation_id == self.operation_3)
        for workorder in workorders:
            # print workorder.name, workorder.product_id, workorder.qty_producing, workorder.state, workorder.operation_id, workorder.workcenter_id, workorder.next_work_order_id
            # self.assertEqual(workorder.operation_id)
            self.assertEqual(workorder.workcenter_id, self.workcenter_1)
        self.assertEqual(kit_wo.state, 'ready')
        self.assertEqual(door_wo_1.state, 'ready')
        self.assertEqual(door_wo_2.state, 'pending')

        # subbom: kit for stone tools
        kit_wo.button_start()
        finished_lot = self.env['stock.production.lot'].create({'product_id': man_order.product_id.id})
        kit_wo.record_production()
        kit_wo.write({
            'final_lot_id': finished_lot.id,
            'qty_producing': 48
        })
        self.assertEqual(kit_wo.state, 'done')

        # first operation of main bom
        finished_lot = self.env['stock.production.lot'].create({'product_id': man_order.product_id.id})
        door_wo_1.record_production()
        door_wo_1.write({
            'final_lot_id': finished_lot.id,
            'qty_producing': 48
        })
        self.assertEqual(door_wo_1.state, 'done')
        self.assertEqual(door_wo_2.state, 'ready')

        # second operation of main bom
        finished_lot = self.env['stock.production.lot'].create({'product_id': man_order.product_id.id})
        door_wo_2.record_production()
        door_wo_2.write({
            'final_lot_id': finished_lot.id,
            'qty_producing': 48
        })
        self.assertEqual(door_wo_2.state, 'done')

        # # first machine (machine A)
        # # self.assertEqual(workorders[0].duration, 40)
        # workorders[0].button_start()
        # finished_lot = self.env['stock.production.lot'].create({'product_id': man_order.product_id.id})
        # workorders[0].write({'final_lot_id': finished_lot.id, 'qty_producing': 48})

        # product_d_move_lot = workorders[0].active_move_lot_ids.filtered(lambda x: x.product_id == self.product_2)
        # product_d_move_lot.write({'lot_id': lot_product_2.id, 'quantity_done': 2})
        # workorders[0].record_production()

        # # Check machine B process....
        # # self.assertEqual(workorders[1].duration, 20, "Workorder duration does not match.")
        # workorders[1].button_start()
        # product_f_move_lot = workorders[1].active_move_lot_ids.filtered(lambda x: x.product_id == self.product_5)
        # product_f_move_lot.write({'lot_id': lot_product_4.id, 'quantity_done': 6})
        # workorders[1].record_production()
        # man_order.button_mark_done()
