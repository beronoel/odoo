# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, models, fields


class product_price_list(models.TransientModel):
    _name = 'product.price_list'
    _description = 'Price List'

    price_list = fields.Many2one('product.pricelist', string='PriceList', required=True)
    qty1 = fields.Integer(string='Quantity-1', default=1)
    qty2 = fields.Integer(string='Quantity-2', default=5)
    qty3 = fields.Integer(string='Quantity-3', default=10)
    qty4 = fields.Integer(string='Quantity-4', default=0)
    qty5 = fields.Integer(string='Quantity-5', default=0)

    @api.multi
    def print_report(self):
        """
        To get the date and print the report
        @return : return report
        """
        context = self.env.context or {}
        datas = {'ids': context.get('active_ids', [])}
        res = self.with_context(context).read(['price_list','qty1', 'qty2','qty3','qty4','qty5'])
        res = res and res[0] or {}
        res['price_list'] = res['price_list'][0]
        datas['form'] = res
        return self.env['report'].with_context(context).get_action('product.report_pricelist', data=datas)
