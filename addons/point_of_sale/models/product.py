# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    available_in_pos = fields.Boolean(string='Available in the Point of Sale', help='Check if you want this product to appear in the Point of Sale', default=True)
    to_weight = fields.Boolean(string='To Weigh With Scale', help="Check if the product should be weighted using the hardware scale integration")
    pos_categ_id = fields.Many2one(
        'pos.category', string='Point of Sale Category',
        help="Those categories are used to group similar products for point of sale.")

    @api.multi
    def unlink(self):
        product_ctx = dict(self.env.context or {}, active_test=False)
        if self.with_context(product_ctx).search_count([('id', 'in', self.ids), ('available_in_pos', '=', True)]):
            if self.env['pos.session'].search_count([('state', '!=', 'closed')]):
                raise UserError(_('You cannot delete a product saleable in point of sale while a session is still opened.'))
        return super(ProductTemplate, self).unlink()

class ProductUomCateg(models.Model):
    _inherit = 'product.uom.categ'

    groupable = fields.Boolean(string='Group Products', help="Check if you want to group products of this category in Point of Sale")

class ProductUom(models.Model):
    _inherit = 'product.uom'

    groupable = fields.Boolean(related='category_id.groupable')
    is_unit = fields.Boolean(compute='_compute_is_unit')

    def _compute_is_unit(self):
        for unit in self.filtered(lambda unit: unit.category_id == self.env.ref('product.product_uom_categ_unit')):
            unit.is_unit = True
