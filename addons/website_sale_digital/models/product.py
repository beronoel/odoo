# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ProductTemplate(models.Model):

    _inherit = ['product.template']

    attachment_count = fields.Integer(compute='_compute_attachment_count', string="File")

    @api.multi
    def _compute_attachment_count(self):
        Attachment = self.env['ir.attachment']
        attachment_data = Attachment.read_group([('res_model', '=', self._name), ('res_id', 'in', self.ids)], ['res_id'], ['res_id'])
        mapped_data = dict([(data['res_id'][0], data['res_id_count']) for data in attachment_data])
        for product_template in self:
            prod_attach_count = Attachment.search_count([('res_model', '=', 'product.product'), ('res_id', 'in', product_template.product_variant_ids.ids)])
            product_template.attachment_count = mapped_data.get(product_template.id, 0) + prod_attach_count

    @api.model
    def _get_product_template_type(self):
        res = super(ProductTemplate, self)._get_product_template_type()
        if 'digital' not in [item[0] for item in res]:
            res.append(('digital', _('Digital Content')))
        return res

    @api.multi
    def action_open_attachments(self):
        self.ensure_one()
        return {
            'name': _('Digital Attachments'),
            'domain': ['|',
                       '&', ('res_model', '=', 'product.product'), ('res_id', 'in', self.product_variant_ids.ids),
                       '&', ('res_model', '=', self._name), ('res_id', '=', self.id)],
            'res_model': 'ir.attachment',
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,form',
            'view_type': 'form',
            'context': "{'default_res_model': '%s','default_res_id': %d}" % (self._name, self.id),
        }


class Product(models.Model):

    _inherit = 'product.product'

    attachment_count = fields.Integer(compute='_compute_attachment_count', string="File")

    @api.multi
    def _compute_attachment_count(self):
        attachment_data = self.env['ir.attachment'].read_group([('res_model', '=', self._name), ('res_id', 'in', self.ids)], ['res_id'], ['res_id'])
        mapped_data = dict([(data['res_id'][0], data['res_id_count']) for data in attachment_data])
        for product in self:
            product.attachment_count = mapped_data.get(product.id, 0)

    @api.multi
    def action_open_attachments(self):
        self.ensure_one()
        return {
            'name': _('Digital Attachments'),
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'res_model': 'ir.attachment',
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,form',
            'view_type': 'form',
            'context': "{'default_res_model': '%s','default_res_id': %d}" % (self._name, self.id),
        }
