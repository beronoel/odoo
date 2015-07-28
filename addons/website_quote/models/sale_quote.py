# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models

import openerp.addons.decimal_precision as dp

class SaleQuoteTemplate(models.Model):
    _name = "sale.quote.template"
    _description = "Sale Quotation Template"

    name = fields.Char('Quotation Template', required=True)
    website_description = fields.Html(string='Description', translate=True)
    quote_line = fields.One2many('sale.quote.line', 'quote_id', string='Quotation Template Lines', copy=True)
    note = fields.Text(string='Terms and conditions')
    options = fields.One2many('sale.quote.option', 'template_id', string='Optional Product Lines', copy=True)
    number_of_days = fields.Integer(string='Quotation Duration', help='Number of days for the validity date computation of the quotation')
    require_payment = fields.Boolean(string='Immediate Payment', help="Require immediate payment by the customer when validating the order from the website quote")

    @api.multi
    def action_open_template(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/quote/template/%d' % self.id
        }


class SaleQuoteLine(models.Model):
    _name = "sale.quote.line"
    _description = "Quotation Template Lines"
    _order = 'sequence, id'

    sequence = fields.Integer(help="Gives the sequence order when displaying a list of sale quote lines.", default=10)
    quote_id = fields.Many2one('sale.quote.template', string='Quotation Template Reference', required=True, ondelete='cascade', index=True)
    name = fields.Text(string='Description', required=True, translate=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], required=True)
    website_description = fields.Html(string='Line Description', compute='_compute_website_description', translate=True)
    price_unit = fields.Float(string='Unit Price', required=True, digits_compute=dp.get_precision('Product Price'))
    discount = fields.Float(digits_compute=dp.get_precision('Discount'))
    product_uom_qty = fields.Float(string='Quantity', required=True, digits_compute=dp.get_precision('Product UoS'), default=1)
    product_uom_id = fields.Many2one('product.uom', string='Unit of Measure ', required=True)

    @api.one
    @api.depends('product_id.product_tmpl_id.quote_description')
    def _compute_website_description(self):
        if self.product_id:
            self.website_description = self.product_id.quote_description or self.product_id.website_description or ''

    @api.onchange('product_id')
    def on_change_product_id(self):
        domain = {}
        product_uom = self.product_uom_id
        self.price_unit = self.product_id.list_price
        self.product_uom_id = self.product_uom_id or self.product_id.uom_id.id
        self.website_description = self.product_id.quote_description or self.product_id.website_description or ''
        self.name = self.product_id.description_sale and self.product_id.name + '\n' + self.product_id.description_sale or self.product_id.name
        if self.product_uom_id != self.product_id.uom_id.id:
            self.price_unit = self.env['product.uom']._compute_price(self.product_id.uom_id.id, self.price_unit, self.product_uom_id.id)
        if not product_uom:
            domain = {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        return {'domain': domain}

    @api.onchange('product_uom_id')
    def on_change_product_uom_id(self):
        if self.product_uom_id:
            self.on_change_product_id()


class SaleQuoteOption(models.Model):
    _name = "sale.quote.option"
    _description = "Quotation Option"

    template_id = fields.Many2one('sale.quote.template', string='Quotation Template Reference', ondelete='cascade', index=True, required=True)
    name = fields.Text(string='Description', required=True, translate=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], required=True)
    website_description = fields.Html(string='Option Description', translate=True)
    price_unit = fields.Float(string='Unit Price', required=True, digits_compute=dp.get_precision('Product Price'))
    discount = fields.Float(digits_compute=dp.get_precision('Discount'))
    uom_id = fields.Many2one('product.uom', string='Unit of Measure', required=True)
    quantity = fields.Float(required=True, digits_compute=dp.get_precision('Product UoS'), default=1)

    @api.onchange('product_id')
    def on_change_product_id(self):
        domain = {}
        product_uom = self.uom_id
        name = self.product_id.name
        if self.product_id.description_sale:
            name += '\n' + self.product_id.description_sale
        self.price_unit = self.product_id.list_price
        self.website_description = self.product_id.product_tmpl_id.quote_description
        self.name = name
        self.uom_id = self.uom_id or self.product_id.product_tmpl_id.uom_id.id

        if self.uom_id != self.product_id.uom_id.id:
            self.price_unit = self.env['product.uom']._compute_price(self.product_id.uom_id.id, self.price_unit, self.uom_id.id)
        if not product_uom:
            domain = {'uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        return {'domain': domain}

    @api.onchange('uom_id')
    def on_change_uom_id(self):
        if self.uom_id:
            self.on_change_product_id()
