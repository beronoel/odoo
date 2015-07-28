# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime
import logging
import uuid

from openerp import api, fields, models

import openerp.addons.decimal_precision as dp

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    _description = "Sales Order Line"

    website_description = fields.Html(string='Line Description', compute='_compute_website_description', store=True)
    option_line_id = fields.One2many('sale.order.option', 'line_id', string='Optional Product Lines')

    @api.one
    def _compute_website_description(self):
        if self.product_id:
            self.website_description = self.product_id.quote_description or self.product_id.website_description


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _default_template_id(self):
        try:
            quote_template = self.env.ref('website_quote.website_quote_template_default')
        except ValueError:
            quote_template = self.template_id
        return quote_template

    access_token = fields.Char(string='Security Token', required=True, copy=False, default=lambda self: str(uuid.uuid4()))
    template_id = fields.Many2one('sale.quote.template', string='Quotation Template', default=_default_template_id, readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    website_description = fields.Html(string='Description')
    options = fields.One2many('sale.order.option', 'order_id', string='Optional Product Lines', readonly=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}, copy=True)
    amount_undiscounted = fields.Float(compute="_compute_amount_undiscounted", string='Amount Before Discount', digits_compute=dp.get_precision('Account'))
    quote_viewed = fields.Boolean(string='Quotation Viewed')
    require_payment = fields.Boolean(string='Immediate Payment', help="Require immediate payment by the customer when validating the order from the website quote")

    @api.multi
    def _compute_amount_undiscounted(self):
        for order in self:
            total = sum(line.product_uom_qty * line.price_unit for line in order.order_line)
            self.amount_undiscounted = total

    @api.onchange('template_id')
    def onchange_template_id(self):
        if not self.template_id:
            return True
        SaleOrderLine = self.env['sale.order.line']
        pricelist = self.env['product.pricelist'].browse(self.pricelist_id)

        context = dict(self.env.context)
        if self.partner_id:
            context.update({'lang': self.partner_id.lang})

        lines = [(5,)]
        quote_template = self.template_id.with_context(context)
        for line in quote_template.quote_line:
            result = SaleOrderLine.with_context(context).product_id_change(False, line.product_id.id, line.product_uom_qty, line.product_uom_id.id, line.product_uom_qty,
                line.product_uom_id.id, line.name, self.partner_id.id, False, True, fields.Date.today(),
                False, self.fiscal_position_id, True)
            data = result.get('value', {})
            price = pricelist.price_get(line.product_id.id, 1).get('pricelist_id') or line.price_unit
            if 'tax_id' in data:
                data['tax_id'] = [(6, 0, data['tax_id'])]
            data.update({
                'name': line.name,
                'price_unit': price,
                'discount': line.discount,
                'product_uom_qty': line.product_uom_qty,
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'website_description': line.website_description,
                'state': 'draft',
            })
            lines.append((0, 0, data))
        options = []
        for option in quote_template.options:
            price = pricelist.price_get(option.product_id.id, 1).get('pricelist_id') or option.price_unit
            options.append((0, 0, {
                'product_id': option.product_id.id,
                'name': option.name,
                'quantity': option.quantity,
                'uom_id': option.uom_id.id,
                'price_unit': price,
                'discount': option.discount,
                'website_description': option.website_description,
            }))
        date = False
        if quote_template.number_of_days > 0:
            date = fields.Date.to_string(datetime.datetime.now() + datetime.timedelta(quote_template.number_of_days))

        self.order_line = lines
        self.website_description = quote_template.website_description
        self.note = quote_template.note
        self.options = options
        self.validity_date = date
        self.require_payment = quote_template.require_payment

    @api.multi
    def action_open_quotation(self):
        self.ensure_one()
        self.quote_viewed = True
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/quote/%s/%s' % (self.id, self.access_token)
        }

    @api.multi
    def get_access_action(self):
        """ Override method that generated the link to access the document. Instead
        of the classic form view, redirect to the online quote if exists. """
        self.ensure_one()
        if not self.template_id:
            return super(SaleOrder, self).get_access_action()
        return {
            'type': 'ir.actions.act_url',
            'url': '/quote/%s' % self.id,
            'target': 'self',
            'res_id': self.id,
        }

    @api.multi
    def action_quotation_send(self):
        self.ensure_one()
        action = super(SaleOrder, self).action_quotation_send()
        if self.template_id:
            template = self.env.ref('website_quote.email_template_edi_sale')
            if template:
                action['context'].update({
                    'default_template_id': template.id,
                    'default_use_template': True
                })
            else:
                _logger.warning("No template found for Quotation")
        return action


class SaleOrderOption(models.Model):
    _name = "sale.order.option"
    _description = "Sale Options"

    order_id = fields.Many2one('sale.order', string='Sale Order Reference', ondelete='cascade', index=True)
    line_id = fields.Many2one('sale.order.line', string='Sale Order Line', on_delete="set null")
    name = fields.Text(string='Description', required=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)])
    website_description = fields.Html(string='Line Description')
    price_unit = fields.Float(string='Unit Price', required=True, digits_compute=dp.get_precision('Product Price'))
    discount = fields.Float(digits_compute=dp.get_precision('Discount'))
    uom_id = fields.Many2one('product.uom', string='Unit of Measure', required=True)
    quantity = fields.Float(required=True, digits_compute=dp.get_precision('Product UoS'), default=1)

    @api.onchange('product_id')
    def on_change_product_id(self):
        domain = {}
        if not self.product_id:
            return {}

        product_uom = self.uom_id
        name = self.product_id.name
        if self.product_id.description_sale:
            name += '\n'+self.product_id.description_sale
        self.price_unit = self.product_id.list_price
        self.website_description = self.product_id.quote_description or self.product_id.website_description
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
