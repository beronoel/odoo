# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.exceptions import UserError
from odoo import models, fields, api, _

# -------------------------
# Packaging related stuff
# -------------------------
class StockPackage(models.Model):
    """
    These are the packages, containing quants and/or other packages
    """
    _name = "stock.quant.package"
    _description = "Physical Packages"
    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = 'name'
    _order = 'parent_left'

    @api.multi
    def name_get(self):
        res = self._complete_name('complete_name', None)
        return res.items()

    @api.multi
    def _complete_name(self, name, args):
        """ Forms complete name of location from parent location to child location.
        @return: Dictionary of values
        """
        res = {}
        for m in self:
            res[m.id] = m.name
            parent = m.parent_id
            while parent:
                res[m.id] = parent.name + ' / ' + res[m.id]
                parent = parent.parent_id
        return res

    @api.depends('quant_ids.location_id', 'quant_ids.company_id', 'quant_ids.owner_id')
    def _get_packages(self):
        """Returns packages from quants for store"""
        res = set()
        for quant in self:
            pack = quant.package_id
            while pack:
                res.add(pack.id)
                pack = pack.parent_id
        return list(res)

    @api.multi
    def _get_package_info(self):
        default_company_id = self.env.user.company_id.id
        for pack in self:
            pack.location_id = False
            pack.owner_id = default_company_id
            pack.company_id = False
            quants = self.env["stock.quant"].search([('package_id', 'child_of', pack.id)], limit=1)
            if quants:
                pack.location_id = quants.location_id.id
                pack.owner_id = quants.owner_id.id
                pack.company_id = quants.company_id.id
            else:
                pack.location_id = False
                pack.owner_id = False
                pack.company_id = False

    @api.depends('quant_ids', 'children_ids', 'parent_id')
    def _get_packages_to_relocate(self):
        res = set()
        for pack in self:
            res.add(pack.id)
            if pack.parent_id:
                res.add(pack.parent_id.id)
        return list(res)

    name = fields.Char('Package Reference', select=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('stock.quant.package') or _('Unknown Pack'))
    complete_name = fields.Char(compute="_complete_name", string="Package Name")
    parent_left = fields.Integer('Left Parent', select=1)
    parent_right = fields.Integer('Right Parent', select=1)
    packaging_id = fields.Many2one('product.packaging', 'Packaging', help="This field should be completed only if everything inside the package share the same product, otherwise it doesn't really makes sense.", select=True)
    location_id = fields.Many2one(compute="_get_package_info", comodel_name='stock.location', string='Location', readonly=True, select=True)
    quant_ids = fields.One2many(comodel_name='stock.quant', inverse_name='package_id', string='Bulk Content', readonly=True)
    parent_id = fields.Many2one('stock.quant.package', 'Parent Package', help="The package containing this item", ondelete='restrict', readonly=True)
    children_ids = fields.One2many(comodel_name='stock.quant.package', inverse_name='parent_id', string='Contained Packages', readonly=True)
    company_id = fields.Many2one(compute="_get_package_info", comodel_name='res.company', string='Company', multi="package", readonly=True, select=True)
    owner_id = fields.Many2one(compute="_get_package_info", comodel_name='res.partner', string='Owner', multi="package", readonly=True, select=True)

    @api.model
    def _check_location_constraint(self, packs):
        '''checks that all quants in a package are stored in the same location. This function cannot be used
           as a constraint because it needs to be checked on pack operations (they may not call write on the
           package)
        '''
        for pack in packs:
            parent = pack
            while parent.parent_id:
                parent = parent.parent_id
            quants = parent.get_content().filtered(lambda x: x.qty > 0)
            location_id = quants and quants[0].location_id.id or False
            if not [quant.location_id.id == location_id for quant in quants]:
                raise UserError(_('Everything inside a package should be in the same location'))
        return True

    @api.multi
    def action_print(self):
        return self.env["report"].with_context(active_ids=self.ids).get_action(self.ids, 'stock.report_package_barcode_small')

    @api.multi
    def unpack(self):
        for package in self:
            package.quant_ids.sudo().write({'package_id': package.parent_id.id or False})
            package.children_ids.write({'parent_id': package.parent_id.id or False})
        #delete current package since it contains nothing anymore
        self.unlink()
        return self.env.ref('stock.action_package_view').read()[0]

    @api.multi
    def get_content(self):
        child_package_ids = self.search([('id', 'child_of', self.ids)]).ids
        return self.env['stock.quant'].search([('package_id', 'in', child_package_ids)])

    @api.multi
    def get_content_package(self):
        quants_ids = self.get_content().ids
        res = self.env.ref('stock.quantsact').read()[0]
        res['domain'] = [('id', 'in', quants_ids)]
        return res

    @api.model
    def _get_product_total_qty(self, package_record, product_id):
        ''' find the total of given product 'product_id' inside the given package 'package_id'''
        all_quant_ids = package_record.get_content()
        total = 0
        for quant in all_quant_ids:
            if quant.product_id.id == product_id:
                total += quant.qty
        return total

    @api.multi
    def _get_all_products_quantities(self):
        '''This function computes the different product quantities for the given package
        '''
        res = {}
        for quant in self.get_content():
            if quant.product_id.id not in res:
                res[quant.product_id.id] = 0
            res[quant.product_id.id] += quant.qty
        return res

    #Remove me?
    @api.multi
    def copy_pack(self, default_pack_values=None, default=None):
        if default is None:
            default = {}
        new_package_id = self.copy(default_pack_values)
        default['result_package_id'] = new_package_id.id
        op_ids = self.env['stock.pack.operation'].search([('result_package_id', '=', self.ids)])
        for op_id in op_ids:
            op_id.copy(default)
