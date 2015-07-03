# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from itertools import chain
import time

from openerp import tools
from openerp import api, fields, models, _

import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError


class PriceType(models.Model):
    """
        The price type is used to points which field in the product form
        is a price and in which currency is this price expressed.
        When a field is a price, you can use it in pricelists to base
        sale and purchase prices based on some fields of the product.
    """
    _name = "product.price.type"
    _description = "Price Type"

    @api.model
    def _price_field_get(self):
        Model = self.env['ir.model.fields']
        fields = Model.search([('model', 'in', (('product.product'), ('product.template'))), ('ttype', '=', 'float')])
        res = []
        for field in fields:
            if not (field.name, field.field_description) in res:
                res.append((field.name, field.field_description))
        return res

    @api.model
    def _get_field_currency(self, fname):
        fields = self.search([('field','=',fname)])
        return fields.currency_id

    @api.model
    def _get_currency(self):
        company = self.env.user.company_id
        if not company:
            company = self.env['res.company'].search([], limit=1)
        return company.currency_id.id

    name = fields.Char(string="Price Name", required=True, translate=True, help="Name of this kind of price.")
    active = fields.Boolean(default=True)
    field = fields.Selection(_price_field_get, string="Product Field", size=32, required=True, help="Associated field in the product form.")
    currency_id = fields.Many2one('res.currency', string="Currency", required=True, default=_get_currency, help="The currency the field is expressed in.")


#----------------------------------------------------------
# Price lists
#----------------------------------------------------------

class ProductPricelistType(models.Model):
    _name = "product.pricelist.type"
    _description = "Pricelist Type"
    name = fields.Char(required=True, translate=True)
    key = fields.Char(required=True, help="Used in the code to select specific prices based on the context. Keep unchanged.")


class ProductPricelist(models.Model):

    _name = "product.pricelist"
    _description = "Pricelist"
    _order = 'name'

    def _get_currency(self):
        company = self.env.user.company_id
        if not company:
            company = self.env['res.company'].search([])
        return company.currency_id.id

    def _pricelist_type_get(self):
        pricelist_type_obj = self.env['product.pricelist.type']
        pricelist_type_ids = pricelist_type_obj.search([], order='name')
        pricelist_types = pricelist_type_ids.read(['key', 'name'])

        res = []
        for typo in pricelist_types:
            res.append((typo['key'], typo['name']))
        return res

    name = fields.Char(string='Pricelist Name', required=True, translate=True)
    active = fields.Boolean(default=True, help="If unchecked, it will allow you to hide the pricelist without removing it.")
    type = fields.Selection(_pricelist_type_get, string='Pricelist Type', required=True)
    version_id = fields.One2many('product.pricelist.version', 'pricelist_id', string='Pricelist Versions', copy=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=_get_currency)
    company_id = fields.Many2one('res.company', string='Company')

    @api.multi
    def name_get(self):
        result = []
        for price_list in self:
            name = price_list.name + ' ('+ price_list.currency_id.name + ')'
            result.append((price_list.id,name))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if name and operator == '=' and not args:
            # search on the name of the pricelist and its currency, opposite of name_get(),
            # Used by the magic context filter in the product search view.
            query_args = {'name': name, 'limit': limit, 'lang': (context or {}).get('lang') or 'en_US'}
            query = """SELECT p.id
                       FROM ((
                                SELECT pr.id, pr.name
                                FROM product_pricelist pr JOIN
                                     res_currency cur ON
                                         (pr.currency_id = cur.id)
                                WHERE pr.name || ' (' || cur.name || ')' = %(name)s
                            )
                            UNION (
                                SELECT tr.res_id as id, tr.value as name
                                FROM ir_translation tr JOIN
                                     product_pricelist pr ON (
                                        pr.id = tr.res_id AND
                                        tr.type = 'model' AND
                                        tr.name = 'product.pricelist,name' AND
                                        tr.lang = %(lang)s
                                     ) JOIN
                                     res_currency cur ON
                                         (pr.currency_id = cur.id)
                                WHERE tr.value || ' (' || cur.name || ')' = %(name)s
                            )
                        ) p
                       ORDER BY p.name"""
            if limit:
                query += " LIMIT %(limit)s"
            self._cr.execute(query, query_args)
            ids = [r[0] for r in self._cr.fetchall()]
            # regular search() to apply ACLs - may limit results below limit in some cases
            records = self.search([('id', 'in', ids)], limit=limit)
            if records:
                return records.name_get()
        return super(ProductPricelist, self).name_search(
            name, args, operator=operator, limit=limit)



    def price_get_multi(self, products_by_qty_by_partner):
        return dict((key, dict((key, price[0]) for key, price in value.items())) for key, value in self.price_rule_get_multi(products_by_qty_by_partner).items())

    def price_rule_get_multi(self, products_by_qty_by_partner):
        """multi products 'price_get'.
           @param ids:
           @param products_by_qty:
           @param partner:
           @param context: {
             'date': Date of the pricelist (%Y-%m-%d),}
           @return: a dict of dict with product_id as key and a dict 'price by pricelist' as value
        """
        results = {}
        for pricelist in self:
            subres = pricelist._price_rule_get_multi(products_by_qty_by_partner)
            for product_id, price in subres.items():
                results.setdefault(product_id, {})
                results[product_id][pricelist.id] = price
        return results

    def _price_get_multi(self, products_by_qty_by_partner):
        return dict((key, price[0]) for key, price in self._price_rule_get_multi(products_by_qty_by_partner).items())

    def _price_rule_get_multi(self, products_by_qty_by_partner):
        context = self.env.context or {}
        date = context.get('date') or fields.Date.context_today(self)
        date = date[0:10]

        products = map(lambda x: x[0], products_by_qty_by_partner)
        # currency_obj = self.env['res.currency']
        # product_obj = self.env['product.template']
        product_uom_obj = self.env['product.uom']
        price_type_obj = self.env['product.price.type']

        if not products:
            return {}

        version = False
        for v in self.version_id:
            if ((v.date_start is False) or (v.date_start <= date)) and ((v.date_end is False) or (v.date_end >= date)):
                version = v
                break
        if not version:
            raise UserError(_("At least one pricelist has no active version !\nPlease create or activate one."))
        categ_ids = {}
        for p in products:
            categ = p.categ_id
            while categ:
                categ_ids[categ.id] = True
                categ = categ.parent_id
        categ_ids = categ_ids.keys()

        is_product_template = products[0]._name == "product.template"
        if is_product_template:
            prod_tmpl_ids = [tmpl.id for tmpl in products]
            # all variants of all products
            prod_ids = [p.id for p in
                        list(chain.from_iterable([t.product_variant_ids for t in products]))]
        else:
            prod_ids = [product.id for product in products]
            prod_tmpl_ids = [product.product_tmpl_id.id for product in products]

        # Load all rules
        self._cr.execute(
            'SELECT i.id '
            'FROM product_pricelist_item AS i '
            'WHERE (product_tmpl_id IS NULL OR product_tmpl_id = any(%s)) '
                'AND (product_id IS NULL OR (product_id = any(%s))) '
                'AND ((categ_id IS NULL) OR (categ_id = any(%s))) '
                'AND (price_version_id = %s) '
            'ORDER BY sequence, min_quantity desc',
            (prod_tmpl_ids, prod_ids, categ_ids, version.id))

        item_ids = [x[0] for x in self._cr.fetchall()]
        items = self.env['product.pricelist.item'].browse(item_ids)

        price_types = {}

        results = {}
        for product, qty, partner in products_by_qty_by_partner:
            results[product.id] = 0.0
            rule_id = False

            # Final unit price is computed according to `qty` in the `qty_uom_id` UoM.
            # An intermediary unit price may be computed according to a different UoM, in
            # which case the price_uom_id contains that UoM.
            # The final price will be converted to match `qty_uom_id`.
            qty_uom_id = context.get('uom') or product.uom_id
            price_uom_id = product.uom_id
            qty_in_product_uom = qty
            if qty_uom_id.id != product.uom_id.id:
                try:
                    qty_in_product_uom = product_uom_obj._compute_qty(
                        context['uom'], qty, product.uom_id.id or product.uos_id.id)
                except UserError:
                    # Ignored - incompatible UoM in context, use default product UoM
                    pass

            price_type = 'standard_price' if self.type == 'purchase' else 'list_price'
            # if Public user try to access standard price from website sale, need to call _price_get.
            price = product.product_tmpl_id._price_get(price_type)
            for rule in items:
                if rule.min_quantity and qty_in_product_uom < rule.min_quantity:
                    continue
                if is_product_template:
                    if rule.product_tmpl_id and product.product_tmpl_id.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and \
                            (product.product_variant_count > 1 or product.product_tmpl_id.product_variant_ids[0].id != rule.product_id.id):
                        # product rule acceptable on template if has only one variant
                        continue
                else:
                    if rule.product_tmpl_id and product.product_tmpl_id.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and product.product_tmpl_id.id != rule.product_id.id:
                        continue
                if rule.base == -1:
                    if rule.base_pricelist_id:
                        price_tmp = rule.base_pricelist_id._price_get_multi([(product,
                                qty, partner)])
                        ptype_src = rule.base_pricelist_id.currency_id
                        price_uom_id = qty_uom_id
                        price = ptype_src.compute(price_tmp, pricelist.currency_id.id, round=False)
                else:
                    if rule.base not in price_types:
                        price_types[rule.base] = price_type_obj.browse(int(rule.base))
                    price_type = price_types[rule.base]

                    # price_get returns the price in the context UoM, i.e. qty_uom_id
                    price_uom_id = qty_uom_id
                    price = price_type.currency_id.compute(product.product_tmpl_id._price_get(price_type.field), self.currency_id, round=False)
                    for seller in product.product_tmpl_id.seller_ids:
                        partner = partner.id if partner and not isinstance(partner, int) else partner
                        if seller.name.id == partner:
                            qty_in_seller = qty
                            seller_uom = seller.product_uom and seller.product_uom.id or False
                            if qty_uom_id != seller_uom:
                                qty_in_seller = qty_uom_id._compute_qty(qty, to_uom_id=seller_uom)
                            for line in seller.pricelist_ids:
                                if line.min_quantity <= qty_in_seller:
                                    price = line.price

                if price is not False:
                    price_limit = price
                    price = price * (1.0+(rule.price_discount or 0.0))
                    if rule.price_round:
                        price = tools.float_round(price, precision_rounding=rule.price_round)

                    convert_to_price_uom = (lambda price: product.product_tmpl_id.uom_id._compute_price(product.product_tmpl_id.uom_id.id,
                                                price, price_uom_id.id))
                    if rule.price_surcharge:
                        price_surcharge = convert_to_price_uom(rule.price_surcharge)
                        price += price_surcharge

                    if rule.price_min_margin:
                        price_min_margin = convert_to_price_uom(rule.price_min_margin)
                        price = max(price, price_limit + price_min_margin)

                    if rule.price_max_margin:
                        price_max_margin = convert_to_price_uom(rule.price_max_margin)
                        price = min(price, price_limit + price_max_margin)

                    rule_id = rule.id
                break

            # Final price conversion to target UoM
            price = product.uom_id._compute_price(product.uom_id.id, price, qty_uom_id.id)
            results[product.product_tmpl_id.id] = (price, rule_id)
        return results

    @api.multi
    def price_get(self, prod_id, qty, partner=None):
        return dict((key, price) for key, price in self.price_rule_get(prod_id, qty, partner=partner).items())

    @api.multi
    def price_rule_get(self, prod_id, qty, partner=None):
        product = self.env['product.product'].browse(prod_id)
        res_multi = self.price_rule_get_multi(products_by_qty_by_partner=[(product, qty, partner)])
        return res_multi[prod_id]


class ProductPricelistVersion(models.Model):
    _name = "product.pricelist.version"
    _description = "Pricelist Version"

    pricelist_id = fields.Many2one('product.pricelist', string='Price List',
        required=True, index=True, ondelete='cascade')
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True, help="When a version is duplicated it is set to non active, so that the " \
        "dates do not overlaps with original version. You should change the dates " \
        "and reactivate the pricelist")
    items_id = fields.One2many('product.pricelist.item',
        'price_version_id', string='Price List Items', required=True, copy=True)
    date_start = fields.Date(string='Start Date', help="First valid date for the version.")
    date_end = fields.Date(string='End Date', help="Last valid date for the version.")
    company_id = fields.Many2one('res.company', related='pricelist_id.company_id',
        readonly=True, string='Company', store=True)

    @api.constrains('date_start', 'date_end')
    @api.one
    def _check_date(self):
        for pricelist_version in self:
            if not pricelist_version.active:
                continue
            where = []
            if pricelist_version.date_start:
                where.append("((date_end>='%s') or (date_end is null))" % (pricelist_version.date_start,))
            if pricelist_version.date_end:
                where.append("((date_start<='%s') or (date_start is null))" % (pricelist_version.date_end,))

            self._cr.execute('SELECT id ' \
                    'FROM product_pricelist_version ' \
                    'WHERE '+' and '.join(where) + (where and ' and ' or '')+
                        'pricelist_id = %s ' \
                        'AND active ' \
                        'AND id <> %s', (
                            pricelist_version.pricelist_id.id,
                            pricelist_version.id))
            if self._cr.fetchall():
                raise UserError("You cannot have 2 pricelist versions that overlap!")
    @api.one
    def copy(self, default=None):
        # set active False to prevent overlapping active pricelist
        # versions
        if not default:
            default = {}
        default['active'] = False
        return super(ProductPricelistVersion, self).copy(default)


class ProductPricelistItem(models.Model):

    _name = "product.pricelist.item"
    _description = "Pricelist item"
    _order = "sequence, min_quantity desc"

    def _price_field_get(self):
        PriceType = self.env['product.price.type']
        price_types = PriceType.search([])
        result = []
        for line in price_types:
            result.append((line.id, line.name))
        result.append((-1, _('Other Pricelist')))
        return result

# Added default function to fetch the Price type Based on Pricelist type.
    def _get_default_base(self, fields):
        PriceType = self.env['product.price.type']
        if fields.get('type') == 'purchase':
            product_price_type_ids = PriceType.search([('field', '=', 'standard_price')])
        elif fields.get('type') == 'sale':
            product_price_type_ids = PriceType.search([('field','=','list_price')])
        else:
            return -1
        if not product_price_type_ids:
            return False
        else:
            pricetype = product_price_type_ids
            return pricetype.id

    name = fields.Char(string='Rule Name', help="Explicit rule name for this pricelist line.")
    price_version_id = fields.Many2one('product.pricelist.version', string='Price List Version', required=True, index=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade', help="Specify a template if this rule only applies to one product template. Keep empty otherwise.")
    product_id = fields.Many2one('product.product', string='Product', ondelete='cascade', help="Specify a product if this rule only applies to one product. Keep empty otherwise.")
    categ_id = fields.Many2one('product.category', string='Product Category', ondelete='cascade', help="Specify a product category if this rule only applies to products belonging to this category or its children categories. Keep empty otherwise.")
    min_quantity = fields.Integer(string='Min. Quantity', required=True, default=0,
        help="For the rule to apply, bought/sold quantity must be greater "
          "than or equal to the minimum quantity specified in this field.\n"
          "Expressed in the default UoM of the product."
        )
    sequence = fields.Integer(required=True, default=5, help="Gives the order in which the pricelist items will be checked. The evaluation gives highest priority to lowest sequence and stops as soon as a matching item is found.")
    base = fields.Selection(_price_field_get, string='Based on', required=True,
                                size=-1, # here use size=-1 to store the values as integers
                                default= _get_default_base, help='Base price for computation. \n Public Price: The base price will be the Sale/public Price. \n Supplier Section on Product or Cost Price : The base price will be the supplier price if it is set, otherwise it will be the cost price. \n Other Pricelist : Computation of the base price based on another Pricelist.')
    base_pricelist_id = fields.Many2one('product.pricelist', string='Other Pricelist')

    price_surcharge = fields.Float(string='Price Surcharge',
        digits= dp.get_precision('Product Price'), help='Specify the fixed amount to add or substract(if negative) to the amount calculated with the discount.')
    price_discount = fields.Float(string='Price Discount', default=0.0, digits=(16,4))
    price_round = fields.Float(string='Price Rounding',
        digits= dp.get_precision('Product Price'),
        help="Sets the price so that it is a multiple of this value.\n" \
          "Rounding is applied after the discount and before the surcharge.\n" \
          "To have prices that end in 9.99, set rounding 10, surcharge -0.01" \
        )
    price_min_margin = fields.Float(string='Min. Price Margin',
        digits= dp.get_precision('Product Price'), help='Specify the minimum amount of margin over the base price.')
    price_max_margin = fields.Float(string='Max. Price Margin',
        digits= dp.get_precision('Product Price'), help='Specify the maximum amount of margin over the base price.')
    company_id = fields.Many2one('res.company', related='price_version_id.company_id',
        readonly=True, string='Company', store=True)

    @api.constrains('base_pricelist_id')
    @api.one
    def _check_recursion(self):
        for obj_list in self:
            if obj_list.base == -1:
                main_pricelist = obj_list.price_version_id.pricelist_id.id
                other_pricelist = obj_list.base_pricelist_id.id
                if main_pricelist == other_pricelist:
                    raise UserError('Error! You cannot assign the Main Pricelist as Other Pricelist in PriceList Item!')

    @api.constrains('price_min_margin', 'price_max_margin')
    @api.one
    def _check_margin(self):
        for item in self:
            if item.price_max_margin and item.price_min_margin and (item.price_min_margin > item.price_max_margin):
                raise UserError('Error! The minimum margin should be lower than the maximum margin.')

    @api.onchange('product_id')
    def product_id_change(self):
        if not self.product_id:
            return {}
        product = self.product_id.read(['code', 'name'])
        if product[0]['code']:
            return {'value': {'name': product[0]['code']}}
        return {}
