# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import math
import re
import time
from .. import _common


from openerp import api, fields, models, tools, _
from openerp.osv import expression
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
import psycopg2

import openerp.addons.decimal_precision as dp
from openerp.tools import float_round, float_compare
from openerp.exceptions import UserError, ValidationError
from openerp.exceptions import except_orm

def ean_checksum(eancode):
    """returns the checksum of an ean string of length 13, returns -1 if the string has the wrong length"""
    if len(eancode) != 13:
        return -1
    oddsum = 0
    evensum = 0
    total = 0
    eanvalue = eancode
    reversevalue = eanvalue[::-1]
    finalean = reversevalue[1:]

    for i in range(len(finalean)):
        if i % 2 == 0:
            oddsum += int(finalean[i])
        else:
            evensum += int(finalean[i])
    total=(oddsum * 3) + evensum

    check = int(10 - math.ceil(total % 10.0)) %10
    return check

def sanitize_ean13(ean13):
    """Creates and returns a valid ean13 from an invalid one"""
    if not ean13:
        return "0000000000000"
    ean13 = re.sub("[A-Za-z]","0",ean13);
    ean13 = re.sub("[^0-9]","",ean13);
    ean13 = ean13[:13]
    if len(ean13) < 13:
        ean13 = ean13 + '0' * (13-len(ean13))
    return ean13[:-1] + str(ean_checksum(ean13))

#----------------------------------------------------------
# UOM
#----------------------------------------------------------

class ProductUomCateg(models.Model):
    _name = 'product.uom.categ'
    _description = 'Product uom categ'
    name = fields.Char(required=True, translate=True)

class ProductUom(models.Model):
    _name = 'product.uom'
    _description = 'Product Unit of Measure'
    _order = "name"

    name = fields.Char('Unit of Measure', required=True, translate=True)
    category_id = fields.Many2one('product.uom.categ', 'Unit of Measure Category', required=True, ondelete='cascade',
        help="Conversion between Units of Measure can only occur if they belong to the same category. The conversion will be made based on the ratios.")
    factor = fields.Float(string='Ratio', required=True, default=1.0,  # force NUMERIC with unlimited precision
        help='How much bigger or smaller this unit is compared to the reference Unit of Measure for this category:\n'\
                '1 * (reference unit) = ratio * (this unit)')
    factor_inv = fields.Float(compute='_factor_inv',  # force NUMERIC with unlimited precision
        inverse='_factor_inv_write',
        string='Bigger Ratio',
        help='How many times this Unit of Measure is bigger than the reference Unit of Measure in this category:\n'\
                '1 * (this unit) = ratio * (reference unit)', required=True)
    rounding = fields.Float(string='Rounding Precision', required=True, default=0.01,
        help="The computed quantity will be a multiple of this value. "\
             "Use 1.0 for a Unit of Measure that cannot be further split, such as a piece.")
    active = fields.Boolean(help="By unchecking the active field you can disable a unit of measure without deleting it.", default=True)
    uom_type = fields.Selection([('bigger','Bigger than the reference Unit of Measure'),
                                  ('reference','Reference Unit of Measure for this category'),
                                  ('smaller','Smaller than the reference Unit of Measure')], string='Type', required=True, default='reference')

    @api.depends('factor')
    def _factor_inv(self):
        for uom in self:
            self.factor_inv = self._compute_factor_inv(uom.factor)

    def _compute_factor_inv(self, factor):
        return factor and (1.0 / factor) or 0.0

    @api.one
    def _factor_inv_write(self):
        self.factor = self._compute_factor_inv(self.factor)

    @api.model
    def name_create(self):
        """ The UoM category and factor are required, so we'll have to add temporary values
            for imported UoMs """
        UomCateg = self.env['product.uom.categ']
        # look for the category based on the english name, i.e. no context on purpose!
        # TODO: should find a way to have it translated but not created until
        # actually used
        categ_misc = 'Unsorted/Imported Units'
        category = UomCateg.search([('name', '=', categ_misc)])
        if category:
            categ_id = category.id
        else:
            categ_id, _ = UomCateg.name_create(categ_misc)
        uom_id = self.create({'category_id': categ_id, 'factor': 1})
        return uom_id.display_name

    @api.model
    def create(self, data):
        if 'factor_inv' in data:
            if data['factor_inv'] != 1:
                data['factor'] = self._compute_factor_inv(data['factor_inv'])
            del(data['factor_inv'])
        return super(ProductUom, self).create(data)

    _sql_constraints = [
        ('factor_gt_zero', 'CHECK (factor!=0)', 'The conversion ratio for a unit of measure cannot be 0!')
    ]

    @api.model
    def _compute_qty(self, from_uom_id, qty, to_uom_id=False, round=True, rounding_method='UP'):
        if not from_uom_id or not qty or not to_uom_id:
            return qty
        uoms = self.browse([from_uom_id, to_uom_id])
        if uoms[0].id == from_uom_id:
            from_unit, to_unit = uoms[0], uoms[-1]
        else:
            from_unit, to_unit = uoms[-1], uoms[0]
        return self._compute_qty_obj(from_unit, qty, to_unit, round=round, rounding_method=rounding_method)

    @api.model
    def _compute_qty_obj(self, from_unit, qty, to_unit, round=True, rounding_method='UP'):
        if from_unit.category_id.id != to_unit.category_id.id:
            if self.env.context.get('raise-exception', True):
                raise UserError(_('Conversion from Product UoM %s to Default UoM %s is not possible as they both belong to different Category!.') % (
                    from_unit.name, to_unit.name))
            else:
                return qty
        amount = qty / from_unit.factor
        if to_unit:
            amount = amount * to_unit.factor
            if round:
                amount = float_round(amount, precision_rounding=to_unit.rounding, rounding_method=rounding_method)
        return amount

    @api.model
    def _compute_price(self, from_uom_id, price, to_uom_id=False):
        if (not from_uom_id or not price or not to_uom_id or (to_uom_id == from_uom_id)):
            return price
        from_unit, to_unit = self.browse([from_uom_id, to_uom_id])
        if from_unit.category_id.id != to_unit.category_id.id:
            return price
        amount = price * from_unit.factor
        if to_uom_id:
            amount = amount / to_unit.factor
        return amount

    @api.onchange('uom_type')
    def onchange_type(self):
        if self.uom_type == 'reference':
            self.factor = 1
            self.factor_inv = 1


#----------------------------------------------------------
# Categories
#----------------------------------------------------------
class ProductCategory(models.Model):
    _name = "product.category"
    _description = "Product Category"
    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = 'sequence, name'
    _order = 'parent_left'

    name = fields.Char(required=True, translate=True, index=True)
    complete_name = fields.Char(compute='_name_get_fnc', string="Name")
    parent_id = fields.Many2one('product.category', string="Parent Category", index=True, ondelete='cascade')
    child_id = fields.One2many('product.category', 'parent_id', string="Child Categories")
    sequence = fields.Integer(index=True, help="Gives the sequence order when displaying a list of product categories.")
    cat_type = fields.Selection([('view', 'View'), ('normal', 'Normal')], string="Category Type", default='normal',
                            help="A category of the view type is a virtual category that can be used as the parent of another category to create a hierarchical structure.")
    parent_left = fields.Integer(string="Left Parent", index=True)
    parent_right = fields.Integer(string="Right Parent", index=True)

    @api.one
    @api.depends('name')
    def _name_get_fnc(self):
        result = self.name_get()
        for values in result:
            self.complete_name = values[1]

    @api.multi
    def name_get(self):
        def get_names(cat):
            """ Return the list [cat.name, cat.parent_id.name, ...] """
            res = []
            while cat:
                res.append(cat.name)
                cat = cat.parent_id
            return res
        return [(cat.id, " / ".join(reversed(get_names(cat)))) for cat in self]

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            # Be sure name_search is symetric to name_get
            categories = name.split(' / ')
            parents = list(categories)
            child = parents.pop()
            domain = [('name', operator, child)]
            if parents:
                names_ids = self.name_search(' / '.join(parents), args=args, operator='ilike', limit=limit)
                category_ids = [name_id[0] for name_id in names_ids]
                if operator in expression.NEGATIVE_TERM_OPERATORS:
                    category_ids = self.search([('id', 'not in', category_ids)])
                    domain = expression.OR([[('parent_id', 'in', category_ids)], domain])
                else:
                    domain = expression.AND([[('parent_id', 'in', category_ids)], domain])
                for i in range(1, len(categories)):
                    domain = [[('name', operator, ' / '.join(categories[-1 - i:]))], domain]
                    if operator in expression.NEGATIVE_TERM_OPERATORS:
                        domain = expression.AND(domain)
                    else:
                        domain = expression.OR(domain)
            category = self.search(expression.AND([domain, args]), limit=limit)
        else:
            category = self.search(args, limit=limit)
        return category.name_get()

    @api.constrains('parent_id')
    def check_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_("Error ! You cannot have 'Parent Category' same as category name."))


class ProducePriceHistory(models.Model):
    """
    Keep track of the ``product.template`` standard prices as they are changed.
    """
    _name = 'product.price.history'
    _rec_name = 'datetime'
    _order = 'datetime desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.user.company_id)
    product_template_id = fields.Many2one('product.template', string="Product Template", required=True, ondelete='cascade')
    datetime = fields.Datetime(string="Historization Time", default=fields.datetime.now())
    cost = fields.Float(string="Historized Cost")


#----------------------------------------------------------
# Product Attributes
#----------------------------------------------------------
class ProductAttribute(models.Model):
    _name = "product.attribute"
    _description = "Product Attribute"
    _order = 'sequence,id'

    name = fields.Char(translate=True, required=True)
    value_ids = fields.One2many('product.attribute.value', 'attribute_id', string="Values", copy=True)
    sequence = fields.Integer(help="Determine the display order")
    attribute_line_ids = fields.One2many('product.attribute.line', 'attribute_id', string='Lines')


class ProductAttributeValue(models.Model):
    _name = "product.attribute.value"
    _order = 'sequence'

    sequence = fields.Integer(help="Determine the display order")
    name = fields.Char(string="Value", translate=True, required=True)
    attribute_id = fields.Many2one('product.attribute', string="Attribute", required=True, ondelete='cascade')
    product_ids = fields.Many2many('product.product', id1='att_id', id2='prod_id', string="Variants", readonly=True)
    price_extra = fields.Float(compute='_get_price_extra', inverse='_set_price_extra', string='Attribute Price Extra', digits=dp.get_precision('Product Price'),
                               help="Price Extra: Extra price for the variant with this attribute value on sale price. eg. 200 price extra, 1000 + 200 = 1200.")
    price_ids = fields.One2many('product.attribute.price', 'value_id', string='Attribute Prices', readonly=True)

    @api.multi
    @api.depends('price_ids.price_extra')
    def _get_price_extra(self):
        context = self.env.context or {}
        price_extra = 0.0
        if not context.get('active_id'):
            self.price_extra = price_extra
        else:
            for obj in self:
                for price_id in obj.price_ids:
                    if price_id.product_tmpl_id.id == self.env.context.get('active_id'):
                        obj.price_extra = price_id.price_extra
                        break

    @api.one
    def _set_price_extra(self):
        ProductObj = self.env['product.attribute.price']
        products = ProductObj.search([('value_id', '=', self.id), ('product_tmpl_id', '=', self.env.context['active_id'])])
        if products:
            products.write({'price_extra': self.price_extra})
        else:
            ProductObj.create({
                'product_tmpl_id': self.env.context['active_id'],
                'value_id': self.id, 'price_extra': self.price_extra,
            })

    @api.multi
    def name_get(self):
        if self.env.context and not self.env.context.get('show_attribute', True):
            return super(ProductAttributeValue, self).name_get()
        result = []
        for value in self:
            result.append([value.id, "%s: %s" % (value.attribute_id.name, value.name)])
        return result

    _sql_constraints = [
        ('value_company_uniq', 'unique (name,attribute_id)', 'This attribute value already exists !')
    ]

    @api.multi
    def unlink(self):
        product_ids = self.env['product.product'].with_context(active_test=False).search([('attribute_value_ids', 'in', self.ids)])
        if product_ids:
            raise UserError(_('The operation cannot be completed:\nYou trying to delete an attribute value with a reference on a product variant.'))
        return super(ProductAttributeValue, self).unlink()


class ProductAttributePrice(models.Model):
    _name = "product.attribute.price"

    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete='cascade')
    value_id = fields.Many2one('product.attribute.value', string='Product Attribute Value', required=True, ondelete='cascade')
    price_extra = fields.Float(digits=dp.get_precision('Product Price'))

class ProductAttributeLine(models.Model):
    _name = "product.attribute.line"
    _rec_name = 'attribute_id'

    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete='cascade')
    attribute_id = fields.Many2one('product.attribute', string='Attribute', required=True, ondelete='restrict')
    value_ids = fields.Many2many('product.attribute.value', id1='line_id', id2='val_id', string='Product Attribute Value(s)')


#----------------------------------------------------------
# Products
#----------------------------------------------------------
class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ['mail.thread']
    _description = "Product Template"
    _order = "name"

    @api.model
    def _default_category(self):
        context = self.env.context or {}
        category = self.env.ref('product.product_category_all')
        if context.get('categ_id'):
            category = context['categ_id']
        return category

    @api.model
    def _default_uom_id(self):
        result = self.env["product.uom"].search([], limit=1, order='id')
        return result

    name = fields.Char(required=True, translate=True, index=True)
    sequence = fields.Integer(default=1, help='Gives the sequence order when displaying a product list')
    product_manager = fields.Many2one('res.users', string='Product Manager')
    description = fields.Text(translate=True,
        help="A precise description of the Product, used only for internal information purposes.")
    description_purchase = fields.Text(string='Purchase Description', translate=True,
        help="A description of the Product that you want to communicate to your suppliers. "
             "This description will be copied to every Purchase Order, Receipt and Supplier Bill/Refund.")
    description_sale = fields.Text(string='Sale Description',translate=True,
        help="A description of the Product that you want to communicate to your customers. "
             "This description will be copied to every Sale Order, Delivery Order and Customer Invoice/Refund")
    rental = fields.Boolean('Can be Rent')
    product_type = fields.Selection([('consu', 'Consumable'), ('service','Service')], string='Product Type', required=True, default='consu', help="Consumable are product where you don't manage stock, a service is a non-material product provided by a company or an individual.")
    categ_id = fields.Many2one('product.category', string='Internal Category', required=True, change_default=True, domain="[('cat_type','=','normal')]", default=_default_category, help="Select category for the current product")
    price = fields.Float(compute='_product_template_price', inverse='_set_product_template_price', digits=dp.get_precision('Product Price'))
    list_price = fields.Float(string='Sale Price', default=1.0, digits=dp.get_precision('Product Price'), help="Base price to compute the customer price. Sometimes called the catalog price.")
    lst_price = fields.Float(related='list_price', string='Public Price', digits=dp.get_precision('Product Price'))
    standard_price = fields.Float(company_dependent=True, digits=dp.get_precision('Product Price'),
                                      help="Cost price of the product template used for standard stock valuation in accounting and used as a base price on purchase orders. "
                                           "Expressed in the default unit of measure of the product.",
                                      string="Cost Price")
    volume = fields.Float(help="Volume is the amount of space that an item you are measuring takes up.")
    weight = fields.Float(string='Gross Weight', digits=dp.get_precision('Stock Weight'), help="The total weight, including contents, packaging, etc.")
    weight_net = fields.Float(string='Net Weight', digits=dp.get_precision('Stock Weight'), help="The weight of the contents, not including any packaging, etc.")
    warranty = fields.Float('Warranty')
    sale_ok = fields.Boolean(string='Can be Sold', default=True, help="Specify if the product can be selected in a sales order line.")
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    state = fields.Selection([('draft', 'In Development'),
        ('sellable','Normal'),
        ('end','End of Lifecycle'),
        ('obsolete','Obsolete')], string='Status')
    uom_id = fields.Many2one('product.uom', string='Unit of Measure', required=True, default=_default_uom_id, help="Default Unit of Measure used for all stock operation.")
    uom_rel_id = fields.Many2one(related='uom_id', readonly=True, string='Default UoM')
    uom_po_id = fields.Many2one('product.uom', string='Purchase Unit of Measure', required=True, default=_default_uom_id, help="Default Unit of Measure used for purchase orders. It must be in the same category than the default unit of measure.")
    uos_id = fields.Many2one('product.uom', string='Unit of Sale',
        help='Specify a unit of measure here if invoicing is made in another unit of measure than inventory. Keep empty to use the default unit of measure.')
    uos_coeff = fields.Float(string='Unit of Measure -> UOS Coeff', default=1.0, digits= dp.get_precision('Product UoS'),
        help='Coefficient to convert default Unit of Measure to Unit of Sale\n'
        ' uos = uom * coeff')
    mes_type = fields.Selection((('fixed', 'Fixed'), ('variable', 'Variable')), string='Measure Type', default='fixed')
    company_id = fields.Many2one('res.company', string='Company', index=True, default=lambda self: self.env['res.company']._company_default_get('product.template'))
    # image: all image fields are base64 encoded and PIL-supported
    image = fields.Binary(help="This field holds the image used as image for the product, limited to 1024x1024px.")
    image_medium = fields.Binary(compute='_compute_image', inverse='_inverse_image_medium',
        string="Medium-sized image", store=True,
        help="Medium-sized image of the product. It is automatically "\
             "resized as a 128x128px image, with aspect ratio preserved, "\
             "only when the image exceeds one of those sizes. Use this field in form views or some kanban views.")
    image_small = fields.Binary(compute='_compute_image', inverse='_inverse_image_small',
        string="Small-sized image", strore=True,
        help="Small-sized image of the product. It is automatically "\
             "resized as a 64x64px image, with aspect ratio preserved. "\
             "Use this field anywhere a small image is required.")
    packaging_ids = fields.One2many(
        'product.packaging', 'product_tmpl_id', string='Logistical Units',
        help="Gives the different ways to package the same product. This has no impact on "
             "the picking order and is mainly used if you use the EDI module.")
    seller_ids = fields.One2many('product.supplierinfo', 'product_tmpl_id', string='Supplier')
    seller_delay = fields.Integer(related='seller_ids.delay', string='Supplier Lead Time',
        help="This is the average delay in days between the purchase order confirmation and the receipts for this product and for the default supplier. It is used by the scheduler to order requests based on reordering delays.")
    seller_qty = fields.Float(related='seller_ids.qty', string='Supplier Quantity',
        help="This is minimum quantity to purchase from Main Supplier.")
    seller_id = fields.Many2one('res.partner', related='seller_ids.name', string='Main Supplier',
        help="Main Supplier who has highest priority in Supplier List.")

    active = fields.Boolean(default=True, help="If unchecked, it will allow you to hide the product without removing it.")
    color = fields.Integer('Color Index')
    is_product_variant = fields.Boolean(compute='_is_product_variant', string='Is a product variant')

    attribute_line_ids = fields.One2many('product.attribute.line', 'product_tmpl_id', string='Product Attributes')
    product_variant_ids = fields.One2many('product.product', 'product_tmpl_id', string='Products', required=True)
    product_variant_count = fields.Integer(compute='_get_product_variant_count', string='# of Product Variants')

    # related to display product product information if is_product_variant
    barcode = fields.Char(related='product_variant_ids.barcode', string='Barcode', oldname='ean13')
    default_code = fields.Char(related='product_variant_ids.default_code', string='Internal Reference')

    @api.multi
    @api.depends('list_price', 'pricelist_id')
    def _product_template_price(self):
        PriceList = self.env['product.pricelist']
        context = self.env.context or {}
        quantity = context.get('quantity') or 1.0
        pricelist = context.get('pricelist', False)
        partner = context.get('partner', False)
        if pricelist:
            qtys = map(lambda x: (x, quantity, partner), self)
            price_list = PriceList.browse(pricelist)
            price = price_list.with_context(context)._price_get_multi(qtys)
            for record in self:
                record.price = price.get(record.id, 0.0)
        for product in self:
            if not product.price: product.price = 0.0

    @api.one
    @api.depends('image')
    def _compute_image(self):
        res = tools.image_get_resized_images(self.image)
        self.image_medium = res['image_medium']
        self.image_small = res['image_small']

    @api.one
    def _inverse_image_medium(self):
        res = tools.image_get_resized_images(self.image_medium)
        self.image = res['image_medium']

    @api.one
    def _inverse_image_small(self):
        res = tools.image_get_resized_images(self.image)
        self.image = res['image']

    @api.multi
    def _is_product_variant(self):
        return self._is_product_variant_impl()

    def _is_product_variant_impl(self):
        return False

    @api.one
    def _set_product_template_price(self):
        Uom = self.env['product.uom']
        context = self.env.context or {}
        price = self.price
        if 'uom' in context:
            uom = self.uos_id or self.uom_id
            price = Uom._compute_price(context['uom'], self.price, uom.id)
        self.list_price = price

    @api.model
    def get_history_price(self, product_tmpl, date=None):
        if date is None:
            date = time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        PriceHistory = self.env['product.price.history']
        history_records= PriceHistory.search([('company_id', '=', self.company_id), ('product_template_id', '=', product_tmpl), ('datetime', '<=', date)], limit=1)
        if history_records:
            return history_records.read(['cost'])['cost']
        return 0.0

    @api.one
    def _set_standard_price(self, value):
        ''' Store the standard price change in order to be able to retrieve the cost of a product template for a given date'''
        PriceHistory = self.env['product.price.history']
        user_company = self.env.user.company_id.id
        company_id = self.env.context.get('force_company', user_company)
        PriceHistory.create({
            'product_template_id': self.id,
            'cost': value,
            'company_id': company_id})

    #could be done using read_group
    @api.multi
    def _get_product_variant_count(self):
        for product in self:
            product.product_variant_count = len(product.product_variant_ids)

    def _price_get_list_price(self, product):
        return 0.0

    @api.multi
    def _price_get(self, ptype='list_price'):
        ProductUom = self.env['product.uom']
        context = self.env.context or {}
        if 'currency_id' in context:
            PriceType = self.env['product.price.type']
            price_type_currency_id = PriceType.search([('field', '=', ptype)], limit=1).currency_id
        for product in self:
            # standard_price field can only be seen by users in base.group_user
            # Thus, in order to compute the sale price from the cost price for users not in this group
            # We fetch the standard price as the superuser
            if ptype != 'standard_price':
                price = product.list_price
            else:
                company_id = product.env.user.company_id.id
                product = product.with_context(force_company=company_id)
                price = product.sudo().list_price
            if ptype == 'list_price':
                price += product._name == "product.product" and product.price_extra
            if 'uom' in context:
                uom = product.uom_id or product.uos_id
                price = ProductUom._compute_price(
                        uom.id, product.list_price, context['uom'])
            # Convert from price_type currency to asked one
            if 'currency_id' in context:
                # Take the price_type currency from the product field
                # This is right cause a field cannot be in more than one currency
                price = price_type_currency_id.compute(price, context['currency_id'])
        return price

    @api.onchange('product_type')
    def onchange_type(self):
        return {}

    @api.onchange('uom_id')
    def onchange_uom(self):
        if self.uom_id:
            self.uom_po_id = self.uom_id

    @api.multi
    def create_variant_ids(self):
        Product = self.env['product.product']
        ctx = self.env.context and self.env.context.copy() or {}
        if ctx.get("create_product_variant"):
            return None
        ctx.update(active_test=False, create_product_variant=True)
        # tmpl_ids = self.browse(cr, uid, ids, context=ctx)
        for tmpl_id in self:
            # list of values combination
            variant_alone = []
            all_variants = [[]]
            for variant_id in tmpl_id.attribute_line_ids:
                if len(variant_id.value_ids) == 1:
                    variant_alone.append(variant_id.value_ids[0])
                temp_variants = []
                for variant in all_variants:
                    for value_id in variant_id.value_ids:
                        temp_variants.append(sorted(variant + [int(value_id)]))
                if temp_variants:
                    all_variants = temp_variants

            # adding an attribute with only one value should not recreate product
            # write this attribute on every product to make sure we don't lose them
            for variant_id in variant_alone:
                product_ids = []
                for product_id in tmpl_id.product_variant_ids:
                    if variant_id.id not in map(int, product_id.attribute_value_ids):
                        product_ids.append(product_id.id)
                Product.browse(product_ids).write({'attribute_value_ids': [(4, variant_id.id)]})

            # check product
            variant_ids_to_active = []
            variants_active_ids = []
            variants_inactive = []
            for product_id in tmpl_id.product_variant_ids:
                variants = sorted(map(int,product_id.attribute_value_ids))
                if variants in all_variants:
                    variants_active_ids.append(product_id.id)
                    all_variants.pop(all_variants.index(variants))
                    if not product_id.active:
                        variant_ids_to_active.append(product_id.id)
                else:
                    variants_inactive.append(product_id)
            if variant_ids_to_active:
                Product.browse(variant_ids_to_active).with_context(ctx).write({'active': True})

            # create new product
            for variant_ids in all_variants:
                values = {
                    'product_tmpl_id': tmpl_id.id,
                    'attribute_value_ids': [(6, 0, variant_ids)]
                }
                record = Product.create(values).with_context(ctx)
                variants_active_ids.append(record)

            # unlink or inactive product
            for variant_id in map(int, variants_inactive):
                try:
                    with self._cr.savepoint(), tools.mute_logger('openerp.sql_db'):
                        self.browse(variant_id).unlink()
                #We catch all kind of exception to be sure that the operation doesn't fail.
                except (psycopg2.Error, except_orm):
                    Product.browse(variant_id).with_context(ctx).write({'active': False})
                    pass
        return True

    @api.model
    def create(self, vals):
        ''' Store the initial standard price in order to be able to retrieve the cost of a product template for a given date'''
        context = self.env.context or {}
        product_template_id = super(ProductTemplate, self.with_context(context)).create(vals)
        if not context or "create_product_product" not in context:
            product_template_id.create_variant_ids()
        product_template_id._set_standard_price(vals.get('standard_price', 0.0))

        # TODO: this is needed to set given values to first variant after creation
        # these fields should be moved to product as lead to confusion
        related_vals = {}
        if vals.get('barcode'):
            related_vals['barcode'] = vals['barcode']
        if vals.get('default_code'):
            related_vals['default_code'] = vals['default_code']
        if related_vals:
            product_template_id.write(related_vals)
        return product_template_id

    @api.multi
    def write(self, vals):
        ''' Store the standard price change in order to be able to retrieve the cost of a product template for a given date'''
        if 'standard_price' in vals:
            for prod_template_id in self:
                prod_template_id._set_standard_price(vals['standard_price'])
        res = super(ProductTemplate, self).write(vals)
        if 'attribute_line_ids' in vals or vals.get('active'):
            self.create_variant_ids()
        if 'active' in vals and not vals.get('active'):
            ctx = self.env.context or {}
            ctx.update(active_test=False)
            products = self.mapped('product_variant_ids')
            products.with_context(ctx).write({'active': vals.get('active')})
        return res

    @api.one
    def copy(self, default=None):
        default = dict(default or {}, name=_("%s (Copy)") % self.name)
        return super(ProductTemplate, self).copy(default=default)

    @api.multi
    @api.constrains('uom_id', 'uom_po_id')
    def _check_uom(self):
        for product in self:
            if product.uom_id.category_id.id != product.uom_po_id.category_id.id:
                raise ValueError(_('Error: The default Unit of Measure and the purchase Unit of Measure must be in the same category.'))

    @api.multi
    def name_get(self):
        context = self.env.context or {}
        if 'partner_id' in context:
            pass
        return super(ProductTemplate, self).name_get()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        # Only use the product.product heuristics if there is a search term and the domain
        # does not specify a match on `product.template` IDs.
        if not name or any(term[0] == 'id' for term in (args or [])):
            return super(ProductTemplate, self).name_search(
                name=name, args=args, operator=operator, limit=limit)

        Product = self.env['product.product']
        results = Product.name_search(
            name, args, operator=operator, limit=limit)
        product_ids = [p[0] for p in results]
        template_ids = [p.product_tmpl_id.id for p in Product.browse(product_ids)]
        # re-apply product.template order + name_get
        return super(ProductTemplate, self).name_search(
            '', args=[('id', 'in', template_ids)],
            operator='ilike', limit=limit)

class Product(models.Model):
    _name = "product.product"
    _description = "Product"
    _inherits = {'product.template': 'product_tmpl_id'}
    _inherit = ['mail.thread']
    _order = 'default_code,name_template'

    price = fields.Float(compute='_product_price', inverse='_set_product_lst_price', digits=dp.get_precision('Product Price'))
    price_extra = fields.Float(compute='_get_price_extra', string='Variant Extra Price', help="This is the sum of the extra price of all attributes", digits=dp.get_precision('Product Price'))
    lst_price = fields.Float(compute='_product_lst_price', inverse='_set_product_lst_price', string='Public Price', digits=dp.get_precision('Product Price'))
    code = fields.Char(compute='_product_code', string='Internal Reference')
    partner_ref = fields.Char(compute='_product_partner_ref', string='Customer ref')
    default_code = fields.Char('Internal Reference', index=True)
    active = fields.Boolean(default=True, help="If unchecked, it will allow you to hide the product without removing it.")
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete="cascade", index=True, auto_join=True)
    barcode = fields.Char(help="International Article Number used for product identification.", oldname='ean13')
    name_template = fields.Char(related='product_tmpl_id.name', string="Template Name", store=True, index=True)
    attribute_value_ids = fields.Many2many('product.attribute.value', id1='prod_id', id2='att_id', string='Attributes', readonly=True, ondelete='restrict')
    is_product_variant = fields.Boolean(compute='_is_product_variant_impl', string='Is a product variant')

    # image: all image fields are base64 encoded and PIL-supported
    image_variant = fields.Binary("Variant Image",
        help="This field holds the image used as image for the product variant, limited to 1024x1024px.")

    image = fields.Binary(compute='_compute_image_variant', inverse='_inverse_image',
        string="Big-sized image",
        help="Image of the product variant (Big-sized image of product template if false). It is automatically "\
             "resized as a 1024x1024px image, with aspect ratio preserved.")
    image_small = fields.Binary(compute='_compute_image_variant', inverse='_inverse_image_small',
        string="Small-sized image",
        help="Image of the product variant (Small-sized image of product template if false).")
    image_medium = fields.Binary(compute='_compute_image_variant', inverse='_inverse_image_medium',
        string="Medium-sized image",
        help="Image of the product variant (Medium-sized image of product template if false).")

    @api.multi
    def _product_price(self):
        PriceList = self.env['product.pricelist']
        context = self.env.context or {}
        quantity = context.get('quantity') or 1.0
        partner = context.get('partner', False)
        pricelist = context.get('pricelist')
        if pricelist:
            # Support context pricelists specified as display_name or ID for compatibility
            qtys = map(lambda x: (x, quantity, partner), self)
            price_list = PriceList.browse(pricelist)
            price = price_list.with_context(context)._price_get_multi(qtys)
            for record in self:
                record.price = price.get(record.id, 0.0)
        for record in self:
            if not record.price: record.price = 0.0

    @api.depends('attribute_value_ids.price_ids.price_extra')
    def _get_price_extra(self):
        for product in self:
            price_extra = 0.0
            for price_id in product.attribute_value_ids.mapped('price_ids'):
                if price_id.product_tmpl_id.id == product.product_tmpl_id.id:
                    price_extra += price_id.price_extra
            product.price_extra = price_extra

    @api.multi
    @api.depends('price_extra', 'lst_price')
    def _product_lst_price(self):
        ProductUom = self.env['product.uom']
        context = self.env.context or {}
        price = 0.0
        for product in self:
            if 'uom' in context:
                uom = product.uos_id or product.uom_id
                price = ProductUom._compute_price(uom.id, product.list_price, context['uom'])
            else:
                price = product.list_price
            product.lst_price = price + product.price_extra

    @api.one
    def _set_product_lst_price(self):
        context = self.env.context or {}
        value = self.price
        ProductUom = self.env['product.uom']
        if 'uom' in context:
            uom = self.uos_id or self.uom_id
            value = ProductUom._compute_price(context['uom'], self.price, uom.id)
        value -= self.price_extra
        self.lst_price = value

    @api.multi
    def _get_partner_code_name(self, product, partner_id):
        for supinfo in product.seller_ids:
            if supinfo.name.id == partner_id:
                return {'code': supinfo.product_code or product.default_code, 'name': supinfo.product_name or product.name}
        res = {'code': product.default_code, 'name': product.name}
        return res

    @api.depends('code', 'name')
    def _product_code(self):
        context = self.env.context or {}
        for product in self:
            product.code = self._get_partner_code_name(product, context.get('partner_id', None))['code']

    @api.multi
    def _product_partner_ref(self):
        context = self.env.context or {}
        for product in self:
            data = self._get_partner_code_name(product, context.get('partner_id', None))
            if not data['code']:
                data['code'] = product.code
            if not data['name']:
                data['name'] = product.name
            product.partner_ref = (data['code'] and ('['+data['code']+'] ') or '') + (data['name'] or '')

    @api.multi
    def _is_product_variant_impl(self):
        for product in self:
            product.is_product_variant = True

    @api.one
    @api.depends('image_variant')
    def _compute_image_variant(self):
        self.image = self.image_variant
        self.image_medium = self.image_variant
        self.image_small = self.image_variant

    @api.one
    def _inverse_image(self):
        self.image_variant = tools.image_resize_image_big(self.image)

    @api.one
    def _inverse_image_medium(self):
        self.image_variant = tools.image_resize_image_medium(self.image_medium)

    @api.one
    def _inverse_image_small(self):
        self.image_variant = tools.image_resize_image_small(self.image_small)

    @api.model
    def view_header_get(self, view_id, view_type):
        context = self.env.context or {}
        header = super(Product, self).view_header_get(view_id, view_type)
        if (context.get('categ_id', False)):
            header = _('Products: ') + self.env['product.category'].browse(context['categ_id']).name
        return header

    @api.multi
    def _get_name_template_ids(self):
        template_ids = self.env['product.product'].search([('product_tmpl_id', 'in', self.ids)])
        return list(set(template_ids))

    @api.multi
    def unlink(self):
        unlink_ids = []
        unlink_product_tmpl_ids = []
        for product in self:
            # Check if product still exists, in case it has been unlinked by unlinking its template
            if not product.exists():
                continue
            tmpl_id = product.product_tmpl_id.id
            # Check if the product is last product of this template
            other_product_ids = self.search([('product_tmpl_id', '=', tmpl_id), ('id', '!=', product.id)])
            if not other_product_ids:
                unlink_product_tmpl_ids.append(tmpl_id)
            unlink_ids.append(product.id)
        super(Product, self.browse(unlink_ids)).unlink()
        # delete templates after calling super, as deleting template could lead to deleting
        # products due to ondelete='cascade'
        self.env['product.template'].browse(unlink_product_tmpl_ids).unlink()

    @api.onchange('product_type')
    def onchange_type(self):
        return {}

    @api.onchange('uom_id', 'uom_po_id')
    def onchange_uom(self):
        if self.uom_id and self.uom_po_id:
            if self.uom_id.category_id.id != self.uom_po_id.category_id.id:
                self.uom_po_id = self.uom_id

    def on_order(self, orderline, quantity):
        pass

    @api.multi
    def name_get(self):
        context = self.env.context or {}

        def _name_get(d):
            name = d.get('name', '')
            code = context.get('display_default_code', True) and d.get('default_code', False)
            if code:
                name = '[%s] %s' % (code, name)
            return (d['id'], name)

        partner_id = context.get('partner_id', False)
        if partner_id:
            partner_ids = [partner_id, self.env['res.partner'].browse(partner_id).commercial_partner_id.id]
        else:
            partner_ids = []

        # all user don't have access to seller and partner
        # check access and use superuser
        self.check_access_rights("read")
        self.check_access_rule("read")

        result = []
        for product in self.sudo():
            variant = ", ".join([v.name for v in product.attribute_value_ids])
            name = variant and "%s (%s)" % (product.name, variant) or product.name
            sellers = []
            if partner_ids:
                sellers = filter(lambda x: x.name.id in partner_ids, product.seller_ids)
            if sellers:
                for s in sellers:
                    seller_variant = s.product_name and (
                        variant and "%s (%s)" % (s.product_name, variant) or s.product_name
                    ) or False
                    mydict = {
                        'id': product.id,
                        'name': seller_variant or name,
                        'default_code': s.product_code or product.default_code,
                    }
                    result.append(_name_get(mydict))
            else:
                mydict = {
                    'id': product.id,
                    'name': name,
                    'default_code': product.default_code,
                }
                result.append(_name_get(mydict))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        context = self.env.context or {}
        if not args:
            args = []
        if name:
            positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
            products = []
            if operator in positive_operators:
                products = self.search([('default_code', '=', name)]+ args, limit=limit)
                if not products:
                    products = self.search([('barcode', '=', name)]+ args, limit=limit)
            if not products and operator not in expression.NEGATIVE_TERM_OPERATORS:
                # Do not merge the 2 next lines into one single search, SQL search performance would be abysmal
                # on a database with thousands of matching products, due to the huge merge+unique needed for the
                # OR operator (and given the fact that the 'name' lookup results come from the ir.translation table
                # Performing a quick memory merge of ids in Python will give much better performance
                products = self.search(args + [('default_code', operator, name)], limit=limit)
                if not limit or len(products) < limit:
                    # we may underrun the limit because of dupes in the results, that's fine
                    limit2 = (limit - len(products)) if limit else False
                    products += self.search(args + [('name', operator, name), ('id', 'not in', products.ids)], limit=limit2)
            elif not products and operator in expression.NEGATIVE_TERM_OPERATORS:
                products = self.search(args + ['&', ('default_code', operator, name), ('name', operator, name)], limit=limit)
            if not products and operator in positive_operators:
                ptrn = re.compile('(\[(.*?)\])')
                res = ptrn.search(name)
                if res:
                    products = self.search([('default_code','=', res.group(2))] + args, limit=limit)
            # still no results, partner in context: search on supplier info as last hope to find something
            if not products and context.get('partner_id'):
                supplier_ids = self.env['product.supplierinfo'].search(
                        [('name', '=', context.get('partner_id')),
                        '|',
                        ('product_code', operator, name),
                        ('product_name', operator, name)
                    ])
                if supplier_ids:
                    products = self.search([('product_tmpl_id.seller_ids', 'in', supplier_ids)], limit=limit)
        else:
            products = self.search(args, limit=limit)
        result = products.name_get()
        return result

    #
    # Could be overrided for variants matrices prices
    #
    @api.multi
    def price_get(self, ptype='list_price'):
        return self.product_tmpl_id._price_get(ptype=ptype)

    @api.one
    def copy(self, default=None):
        context = self.env.context or {}
        if context.get('variant'):
            # if we copy a variant or create one, we keep the same template
            default['product_tmpl_id'] = self.product_tmpl_id.id
        elif 'name' not in default:
            default['name'] = _("%s (copy)") % (self.name,)
        return super(Product, self.with_context(context)).copy(default=default)

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        context = self.env.context or {}
        if context.get('search_default_categ_id'):
            args.append((('categ_id', 'child_of', context['search_default_categ_id'])))
        return super(Product, self).search(args, offset=offset, limit=limit, order=order, count=count)

    @api.multi
    def open_product_template(self):
        """ Utility method used to add an "Open Template" button in product views """
        return {'type': 'ir.actions.act_window',
                'res_model': 'product.template',
                'view_mode': 'form',
                'res_id': self.product_tmpl_id.id,
                'target': 'new'}

    @api.model
    def create(self, vals):
        ctx = dict(self.env.context or {}, create_product_product=True)
        return super(Product, self.with_context(ctx)).create(vals)

    @api.multi
    def need_procurement(self):
        return False

#### Method does not seems to be used from anywhere, Could be removed
    @api.one
    def _compute_uos_qty(self, uom, qty, uos):
        '''
        Computes product's invoicing quantity in UoS from quantity in UoM.
        Takes into account the
        :param uom: Source unit
        :param qty: Source quantity
        :param uos: Target UoS unit.
        '''
        if not uom or not qty or not uos:
            return qty
        Uom = self.env['product.uom']
        uos_id, uom_id = self.browse([uos, uom])
        if self.uos_id:  # Product has UoS defined
            # We cannot convert directly between units even if the units are of the same category
            # as we need to apply the conversion coefficient which is valid only between quantities
            # in product's default UoM/UoS
            qty_default_uom = Uom._compute_qty_obj(uom_id, qty, self.uom_id)  # qty in product's default UoM
            qty_default_uos = qty_default_uom * self.uos_coeff
            return Uom._compute_qty_obj(self.uos_id, qty_default_uos, uos_id)
        else:
            return Uom._compute_qty_obj(uom_id, qty, uos_id)


class ProductPackaging(models.Model):
    _name = "product.packaging"
    _description = "Packaging"
    _order = 'sequence'

    name = fields.Char('Packaging Type', required=True)
    sequence = fields.Integer(default=1, help="The first in the sequence is the default one.")
    product_tmpl_id = fields.Many2one('product.template', string='Product')
    qty = fields.Float(string='Quantity by Package',
        help="The total number of products you can put by pallet or box.")


class ProductSupplierinfo(models.Model):
    _name = "product.supplierinfo"
    _description = "Information about a product supplier"
    _order = 'sequence'

    @api.multi
    @api.depends('min_qty')
    def _calc_qty(self):
        for record in self:
            record.qty = record.min_qty

    name = fields.Many2one('res.partner', string='Supplier', required=True, domain=[('supplier', '=', True)], ondelete='cascade', help="Supplier of this product")
    product_name = fields.Char(string='Supplier Product Name', help="This supplier's product name will be used when printing a request for quotation. Keep empty to use the internal one.")
    product_code = fields.Char(string='Supplier Product Code', help="This supplier's product code will be used when printing a request for quotation. Keep empty to use the internal one.")
    sequence = fields.Integer(default=1, help="Assigns the priority to the list of product supplier.")
    product_uom = fields.Many2one('product.uom', related='product_tmpl_id.uom_po_id', string="Supplier Unit of Measure", readonly=True, store=True, help="This comes from the product form.")
    min_qty = fields.Float(string='Minimal Quantity', required=True, help="The minimal quantity to purchase to this supplier, expressed in the supplier Product Unit of Measure if not empty, in the default unit of measure of the product otherwise.")
    qty = fields.Float(compute=_calc_qty, store=True, string='Quantity', help="This is a quantity which is converted into Default Unit of Measure.")
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete='cascade', index=True, oldname='product_id')
    delay = fields.Integer(string='Delivery Lead Time', required=True, default=1, help="Lead time in days between the confirmation of the purchase order and the receipt of the products in your warehouse. Used by the scheduler for automatic computation of the purchase order planning.")
    pricelist_ids = fields.One2many('pricelist.partnerinfo', 'suppinfo_id', string='Supplier Pricelist', copy=True)
    company_id = fields.Many2one('res.company', string='Company', index=True, default=lambda self: self.env['res.company']._company_default_get('product.supplierinfo'))


class PricelistPartnerinfo(models.Model):
    _name = 'pricelist.partnerinfo'
    _order = 'min_quantity asc'

    name = fields.Char(string='Description')
    suppinfo_id = fields.Many2one('product.supplierinfo', string='Partner Information', required=True, ondelete='cascade')
    min_quantity = fields.Float(string='Quantity', required=True, help="The minimal quantity to trigger this rule, expressed in the supplier Unit of Measure if any or in the default Unit of Measure of the product otherrwise.")
    price = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'), help="This price will be considered as a price for the supplier Unit of Measure if any or the default Unit of Measure of the product otherwise")


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.constrains('rounding')
    def _check_main_currency_rounding(self):
        self.env.cr.execute('SELECT digits FROM decimal_precision WHERE name like %s', ('Account',))
        digits = self.env.cr.fetchone()
        if digits and len(digits):
            digits = digits[0]
            main_currency = self.env.user.company_id.currency_id
            for currency_id in self:
                if currency_id == main_currency.id:
                    if float_compare(main_currency.rounding, 10 ** -digits, precision_digits=6) == -1:
                        raise UserError('Error! You cannot define a rounding factor for the company\'s main currency that is smaller than the decimal precision of \'Account\'.')
        return True


class DecimalPrecision(models.Model):
    _inherit = 'decimal.precision'

    @api.constrains('digits')
    def _check_main_currency_rounding(self):
        self.env.cr.execute('SELECT id, digits FROM decimal_precision WHERE name like %s', ('Account',))
        res = self.env.cr.fetchone()
        if res and len(res):
            account_precision_id, digits = res
            main_currency = self.env.user.company_id.currency_id
            for decimal_precision in self:
                if decimal_precision == account_precision_id:
                    if float_compare(main_currency.rounding, 10 ** -digits, precision_digits=6) == -1:
                        raise UserError('Error! You cannot define the decimal precision of \'Account\' as greater than the rounding factor of the company\'s main currency')
        return True
