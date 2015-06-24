# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, tools, _
from openerp.http import request


class Website(models.Model):
    _inherit = 'website'

    pricelist_id = fields.Many2one('product.pricelist', related='user_id.partner_id.property_product_pricelist', string='Default Pricelist')
    currency_id = fields.Many2one('res.currency', related='pricelist_id.currency_id', string='Default Currency')
    salesperson_id = fields.Many2one('res.users', string='Salesperson')
    salesteam_id = fields.Many2one('crm.team', string='Sales Team')
    website_pricelist_ids = fields.One2many('website_pricelist', 'website_id',
                                            string='Price list available for this Ecommerce/Website')

    @tools.ormcache('self.env.uid', 'country_code', 'show_visible', 'website_pl', 'current_pl', 'all_pl')
    def _get_pl(self, country_code, show_visible, website_pl, current_pl, all_pl):
        """ Return the list of pricelists that can be used on website for the current user.

        :param str country_code: code iso or False, If set, we search only price list available for this country
        :param bool show_visible: if True, we don't display pricelist where selectable is False (Eg: Code promo)
        :param int website_pl: The default pricelist used on this website
        :param int current_pl: The current pricelist used on the website
                               (If not selectable but the current pricelist we had this pricelist anyway)
        :param list all_pl: List of all pricelist available for this website

    :returns: list of pricelist
        """
        pcs = []

        if country_code:
            groups = self.env['res.country.group'].search([('country_ids.code', '=', country_code)])
            for cgroup in groups:
                for pll in cgroup.website_pricelist_ids:
                    if not show_visible or pll.selectable or pll.pricelist_id.id == current_pl:
                        pcs.append(pll.pricelist_id)

        if not pcs:  # no pricelist for this country, or no GeoIP
            pcs = [pll.pricelist_id for pll in all_pl
                   if not show_visible or pll.selectable or pll.pricelist_id.id == current_pl]

        partner = self.env.user.partner_id
        if not pcs or partner.property_product_pricelist.id != website_pl:
            pcs.append(partner.property_product_pricelist)
        pcs = list(set(pcs))  # remove duplicate
        pcs.sort(key=lambda x: x.name)  # sort by name
        return pcs

    @api.model
    def get_pricelist_available(self, show_visible=False):
        """ Return the list of pricelists that can be used on website for the current user.
        Country restrictions will be detected with GeoIP (if installed).

        :param str country_code: code iso or False, If set, we search only price list available for this country
        :param bool show_visible: if True, we don't display pricelist where selectable is False (Eg: Code promo)

        :returns: list of pricelist
        """
        isocountry = request.session.geoip and request.session.geoip.get('country_code') or False
        return self._get_pl(
            isocountry,
            show_visible,
            request.website.pricelist_id.id,
            request.session.get('website_sale_current_pl'),
            request.website.website_pricelist_ids
        )

    @api.multi
    def is_pricelist_available(self, pl_id):
        """ Return a boolean to specify if a specific pricelist can be manually set on the website.
        Warning: It check only if pricelist is in the 'selectable' pricelists or the current pricelist.

        :param int pl_id: The pricelist id to check

        :returns: Boolean, True if valid / available
        """
        self.ensure_one()
        return pl_id in [ppl.id for ppl in self.get_pricelist_available(show_visible=False)]

    @api.model
    def get_current_pricelist(self):
        """
        :returns: The current pricelist record
        """
        pl_id = request.session.get('website_sale_current_pl')
        if pl_id:
            return self.env['product.pricelist'].browse(pl_id)
        else:
            pl = self.env.user.partner_id.property_product_pricelist
            request.session['website_sale_current_pl'] = pl.id
            return pl

    @api.multi
    def sale_product_domain(self):
        return [("sale_ok", "=", True)]

    @api.multi
    def sale_get_order(self, force_create=False, code=None, update_pricelist=False, force_pricelist=False):
        """ Return the current sale order after mofications specified by params.

        :param bool force_create: Create sale order if not already existing
        :param str code: Code to force a pricelist (promo code)
                         If empty, it's a special case to reset the pricelist with the first available else the default.
        :param bool update_pricelist: Force to recompute all the lines from sale order to adapt the price with the current pricelist.
        :param int force_pricelist: pricelist_id - if set,  we change the pricelist with this one

        :returns: browse record for the current sale order
        """
        self.ensure_one()
        partner = self.env.user.partner_id
        SaleOrderSudo = self.env['sale.order'].sudo()
        sale_order_id = request.session.get('sale_order_id') or (partner.last_website_so_id.id if partner.last_website_so_id and partner.last_website_so_id.state == 'draft' else False)

        sale_order = None
        pricelist_id = request.session.get('website_sale_current_pl')

        if force_pricelist and self.env['product.pricelist'].search_count([('id', '=', force_pricelist)]):
            pricelist_id = force_pricelist
            request.session['website_sale_current_pl'] = pricelist_id
            update_pricelist = True

        # create so if needed
        if not sale_order_id and (force_create or code):
            # TODO cache partner_id session
            affiliate_id = request.session.get('affiliate_id')
            salesperson_id = affiliate_id if self.sudo(affiliate_id).exists() else request.website.salesperson_id.id

            values = {
                'partner_id': partner.id,
                'pricelist_id': pricelist_id,
                'team_id': self.salesteam_id.id,
            }
            sale_order = SaleOrderSudo.create(values)
            sale_order.onchange_partner_id()
            sale_order.user_id = salesperson_id or self.salesperson_id.id

            request.session['sale_order_id'] = sale_order.id

            if request.website.partner_id.id != partner.id:
                partner.sudo().write({'last_website_so_id': sale_order.id})

        if sale_order_id:
            sale_order = SaleOrderSudo.browse(sale_order_id)
            if not sale_order.exists():
                request.session['sale_order_id'] = None
                return None

            # check for change of pricelist with a coupon
            pricelist_id = pricelist_id or partner.property_product_pricelist.id

            # check for change of partner_id ie after signup
            if sale_order.partner_id.id != partner.id and request.website.partner_id.id != partner.id:
                flag_pricelist = False
                if pricelist_id != sale_order.pricelist_id.id:
                    flag_pricelist = True

                sale_order.onchange_partner_id()
                values = {}
                if self.pricelist_id.id != pricelist_id:
                    values['pricelist_id'] = pricelist_id
                    update_pricelist = True

                values['partner_id'] = partner.id
                sale_order.write(values)

                if flag_pricelist:
                    update_pricelist = True

            if (code and code != sale_order.pricelist_id.code) or \
               (code is not None and code == '' and request.session.get('sale_order_code_pricelist_id') and request.session.get('sale_order_code_pricelist_id') != ''):  # empty code so reset
                pricelist = request.env['product.pricelist'].search([('code', '=', code)], limit=1)
                if pricelist:
                    pricelist_id = pricelist.id
                    request.session['sale_order_code_pricelist_id'] = pricelist_id
                    request.session['website_sale_current_pl'] = pricelist_id
                    update_pricelist = True
                elif code == '' and request.session['website_sale_current_pl'] == request.session['sale_order_code_pricelist_id']:
                    request.session['website_sale_current_pl'] = partner.property_product_pricelist.id
                    request.session['sale_order_code_pricelist_id'] = False
                    update_pricelist = True
            # update the pricelist
            if update_pricelist:
                sale_order.pricelist_id = pricelist_id
                for line in sale_order.order_line:
                    if line.exists():
                        sale_order._cart_update(product_id=line.product_id.id, line_id=line.id, add_qty=0)

            # update browse record
            if (code and code != sale_order.pricelist_id.code) or sale_order.partner_id.id != partner.id or force_pricelist:
                sale_order = SaleOrderSudo.browse(sale_order.id)
        return sale_order

    def sale_get_transaction(self):
        tx_id = request.session.get('sale_transaction_id')
        if tx_id:
            tx = self.env['payment.transaction'].sudo().search([('id', '=', tx_id), ('state', 'not in', ['cancel'])], limit=1)
            if tx:
                return tx
            else:
                request.session['sale_transaction_id'] = False
        return False

    @api.model
    def sale_reset(self):
        request.session.update({
            'sale_order_id': False,
            'sale_transaction_id': False,
            'sale_order_code_pricelist_id': False,
            'website_sale_current_pl': False,
        })


class WebsitePricelist(models.Model):
    _name = 'website_pricelist'
    _description = 'Website Pricelist'

    name = fields.Char(compute="_compute_display_name", string='Pricelist Name')

    def _compute_display_name(self):
        for pricelist in self:
            self.name = _("Website Pricelist for %s") % pricelist.pricelist_id.name

    website_id = fields.Many2one('website', string="Website", required=True)
    selectable = fields.Boolean(help="Allow the end user to choose this price list")
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    country_group_ids = fields.Many2many('res.country.group', 'res_country_group_website_pricelist_rel',
                                         'website_pricelist_id', 'res_country_group_id', string='Country Groups')

    def clear_cache(self):
        # website._get_pl() is cached to avoid to recompute at each request the
        # list of available pricelists. So, we need to invalidate the cache when
        # we change the config of website price list to force to recompute.
        website = self.pool['website']
        website._get_pl.clear_cache(website)

    @api.model
    def create(self, data):
        res = super(WebsitePricelist, self).create(data)
        self.clear_cache()
        return res

    @api.multi
    def write(self, data):
        res = super(WebsitePricelist, self).write(data)
        self.clear_cache()
        return res

    @api.multi
    def unlink(self):
        res = super(WebsitePricelist, self).unlink()
        self.clear_cache()
        return res
