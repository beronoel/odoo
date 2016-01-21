# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPackOperationLot(models.Model):
    _name = "stock.pack.operation.lot"
    _description = "Specifies lot/serial number for pack operations that need it"

    @api.multi
    def _get_plus(self):
        for packlot in self:
            if packlot.operation_id.product_id.tracking == 'serial':
                packlot.plus_visible = (packlot.qty == 0.0)
            else:
                packlot.plus_visible = (packlot.qty_todo == 0.0) or (packlot.qty < packlot.qty_todo)

    operation_id = fields.Many2one('stock.pack.operation')
    qty = fields.Float('Done', default=1.0)
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number')
    lot_name = fields.Char()
    qty_todo = fields.Float('To Do', default=0.0)
    plus_visible = fields.Boolean(compute="_get_plus", default=True)

    @api.multi
    @api.constrains('lot_id', 'lot_name')
    def _check_lot(self):
        for packlot in self:
            if not packlot.lot_name and not packlot.lot_id:
                raise UserError(_('Lot is required'))
        return True

    _sql_constraints = [
        ('qty', 'CHECK(qty >= 0.0)', 'Quantity must be greater than or equal to 0.0!'),
        ('uniq_lot_id', 'unique(operation_id, lot_id)', 'You have already mentioned this lot in another line'),
        ('uniq_lot_name', 'unique(operation_id, lot_name)', 'You have already mentioned this lot name in another line')]

    @api.multi
    def do_plus(self):
        for packlot in self:
            packlot.write({'qty': packlot.qty + 1})
        pack = self[0].operation_id
        qty_done = sum([x.qty for x in pack.pack_lot_ids])
        pack.write({'qty_done': qty_done})
        return pack.split_lot()

    @api.multi
    def do_minus(self):
        for packlot in self:
            packlot.write({'qty': packlot.qty - 1})
        pack = self[0].operation_id
        qty_done = sum([x.qty for x in pack.pack_lot_ids])
        pack.write({'qty_done': qty_done})
        return pack.split_lot()
