# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import api, fields, models


class MakeProcurement(models.TransientModel):
    _name = 'make.procurement'
    _description = 'Make Procurements'

    @api.multi
    @api.onchange('product_id')
    def onchange_product_id(self, prod_id):
        product = self.env['product.product'].browse(prod_id)
        return {'value': {
            'uom_id': product.uom_id.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_variant_count': product.product_tmpl_id.product_variant_count
        }}

    qty = fields.Float(string='Quantity', digits=(16, 2), required=True, default=1.0)
    res_model = fields.Char()
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_tmpl_id = fields.Many2one('product.template', string='Template', required=True)
    product_variant_count = fields.Integer(related='product_tmpl_id.product_variant_count', string='Variant Number')
    uom_id = fields.Many2one('product.uom', string='Unit of Measure', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    date_planned = fields.Date(string='Planned Date', required=True, default=fields.Date.context_today)
    route_ids = fields.Many2many('stock.location.route', string='Preferred Routes')

    @api.multi
    def make_procurement(self):
        """ Creates procurement order for selected product. """
        ProcurementOrder = self.env['procurement.order']

        for proc in self:
            procurement = ProcurementOrder.create({
                'name': 'INT: ' + str(self.env.user.login),
                'date_planned': proc.date_planned,
                'product_id': proc.product_id.id,
                'product_qty': proc.qty,
                'product_uom': proc.uom_id.id,
                'warehouse_id': proc.warehouse_id.id,
                'location_id': proc.warehouse_id.lot_stock_id.id,
                'company_id': proc.warehouse_id.company_id.id,
                'route_ids': [(6, 0, proc.route_ids.ids)],
            })
            procurement.signal_workflow('button_confirm')

        proc_tree = self.env.ref('procurement.procurement_tree_view')
        proc_form = self.env.ref('procurement.procurement_form_view')

        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'procurement.order',
            'res_id': procurement.id,
            'views': [(proc_form.id, 'form'), (proc_tree.id, 'tree')],
            'type': 'ir.actions.act_window',
         }

    @api.model
    def default_get(self, fields):
        cxt = self.env.context
        record = cxt.get('active_id')

        if cxt.get('active_model') == 'product.template':
            product_ids = self.env['product.product'].search([('product_tmpl_id', '=', record)], limit=1)
            if product_ids:
                record_id = product_ids.id

        res = super(MakeProcurement, self).default_get(fields)

        if record_id and 'product_id' in fields:
            proxy = self.env['product.product']
            product = proxy.search([('id', '=', record_id)], limit=1)
            if product:
                res['product_id'] = product.id
                res['uom_id'] = product.uom_id.id

        if 'warehouse_id' in fields:
            warehouse_id = self.env['stock.warehouse'].search([], limit=1)
            res['warehouse_id'] = warehouse_id.id if warehouse_id else False

        return res

    @api.model
    def create(self, values):
        if values.get('product_id'):
            values.update(self.onchange_product_id(values['product_id'])['value'])
        return super(MakeProcurement, self).create(values)
