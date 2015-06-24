# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import random
from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    website_order_line = fields.One2many(
        'sale.order.line', 'order_id',
        string='Order Lines displayed on Website', readonly=True,
        help='Order Lines to be displayed on the website. They should not be used for computation purpose.',
    )
    cart_quantity = fields.Integer(compute='_compute_cart_info')
    payment_acquirer_id = fields.Many2one('payment.acquirer', 'Payment Acquirer', on_delete='set null', copy=False)
    payment_tx_id = fields.Many2one('payment.transaction', 'Transaction', on_delete='set null', copy=False)
    only_services = fields.Boolean(compute='_compute_cart_info')

    @api.depends('website_order_line')
    def _compute_cart_info(self):
        for order in self:
            order.cart_quantity = int(sum(order.mapped('website_order_line.product_uom_qty')))
            order.only_services = all(order.website_order_line.filtered(lambda l: (l.product_id and l.product_id.type == 'service')))

    @api.model
    def _get_errors(self, order):
        return []

    @api.model
    def _get_website_data(self, order):
        return {
            'partner': order.partner_id.id,
            'order': order
        }

    @api.multi
    def _cart_find_product_line(self, product_id=None, line_id=None, **kwargs):
        for so in self:
            domain = [('order_id', '=', so.id), ('product_id', '=', product_id)]
            if line_id:
                domain.append(('id', '=', line_id))
            return self.env['sale.order.line'].sudo().search(domain).ids

    @api.multi
    def _website_product_id_change(self, order_id, product_id, qty=0):
        product = self.env['product.product'].browse(product_id)
        values = {
            'product_id': product_id,
            'name': product.display_name,
            'product_uom_qty': qty,
            'order_id': order_id,
            'product_uom': product.uom_id.id,
        }
        if product.description_sale:
            values['name'] += '\n' + product.description_sale
        return values

    @api.multi
    def _cart_update(self, product_id=None, line_id=None, add_qty=0, set_qty=0, **kwargs):
        """ Add or set product quantity, add_qty can be negative """
        OrderLine = self.env['sale.order.line'].sudo()

        quantity = 0
        for so in self:
            if so.state != 'draft':
                request.session['sale_order_id'] = None
                raise UserError(_('It is forbidden to modify a sale order which is not in draft status'))
            if line_id is not False:
                line_ids = so._cart_find_product_line(product_id, line_id, **kwargs)
                if line_ids:
                    line_id = line_ids[0]
                    line = OrderLine.browse(line_ids[0])

            # Create line if no line with product_id can be located
            if not line_id:
                values = so._website_product_id_change(so.id, product_id, qty=1)
                line = OrderLine.create(values)
                line.product_id_change()
                if add_qty:
                    add_qty -= 1

            # compute new quantity
            if set_qty:
                quantity = set_qty
            elif add_qty >= 0:
                quantity = line.product_uom_qty + add_qty

            # Remove zero of negative lines
            if quantity <= 0:
                line.unlink()
            else:
                # update line
                values = so._website_product_id_change(so.id, product_id, qty=quantity)
                values['product_uom_qty'] = quantity
                line.write(values)

        return {'line_id': line.id, 'quantity': quantity}

    def _cart_accessories(self):
        for order in self:
            s = set(j.id for l in (order.website_order_line or []) for j in (l.product_id.accessory_product_ids or []) if j.website_published)
            s -= set(l.product_id.id for l in order.order_line)
            product_ids = random.sample(s, min(len(s), 3))
            return self.env['product.product'].browse(product_ids)
