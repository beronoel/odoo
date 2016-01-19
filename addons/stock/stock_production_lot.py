# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _

#----------------------------------------------------------
# Production Lot
#----------------------------------------------------------

class StockProductionLot(models.Model):
    _name = 'stock.production.lot'
    _inherit = ['mail.thread']
    _description = 'Lot/Serial'

    name = fields.Char('Serial Number', required=True, default=lambda x: x.env['ir.sequence'].next_by_code('stock.lot.serial'), help="Unique Serial Number")
    ref = fields.Char('Internal Reference', help="Internal reference number in case it differs from the manufacturer's serial number")
    product_id = fields.Many2one('product.product', 'Product', required=True, domain=[('type', 'in', ['product', 'consu'])], default=lambda x: x._context.get('product_id'))
    quant_ids = fields.One2many('stock.quant', 'lot_id', 'Quants', readonly=True)
    create_date = fields.Datetime('Creation Date')

    _sql_constraints = [
        ('name_ref_uniq', 'unique (name, product_id)', 'The combination of serial number and product must be unique !'),
    ]

    @api.multi
    def action_traceability(self):
        """ It traces the information of lots
        @param self: The object pointer.
        @return: A dictionary of values
        """
        quants = self.env["stock.quant"].search([('lot_id', 'in', self.ids)])
        moves = set()
        for quant in quants:
            moves |= {move.id for move in quant.history_ids}
        if moves:
            return {
                'domain': "[('id','in',[" + ','.join(map(str, list(moves))) + "])]",
                'name': _('Traceability'),
                'view_mode': 'tree,form',
                'view_type': 'form',
                'context': {'tree_view_ref': 'stock.view_move_tree'},
                'res_model': 'stock.move',
                'type': 'ir.actions.act_window',
                    }
        return False
