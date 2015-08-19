# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.tools import drop_view_if_exists

class ReportProductMarginView(models.Model):
    _name = "report.product.margin"
    _description = "Product Margin Statistics"
    _auto = False

    invoice_date = fields.Date(readonly=True)
    invoice_state = fields.Selection(selection=[
            ('open','Open'),
            ('paid','Paid'),
            ('proforma','Pro-forma'),
            ('proforma2', 'Pro-forma')
        ], readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", readonly=True,
        help="Invoice currency")
    total_margin = fields.Float(readonly=True,
        help="Total Margin - Substraction of the customer's invoices' total and supplier's invoices' total")
    expected_margin = fields.Float(readonly=True,
        help="Expected Margin - Substration of the list price and cost price")
    sale_avg_price = fields.Float(string='Avg. Sale Price',
        help="Avg. Price in Customer Invoices.", readonly=True)
    sale_num_invoiced = fields.Float(string='#Products Sold', readonly=True,
        help="Sum of Products Quantity in Customer Invoices")
    sales_gap = fields.Float(readonly=True,
        help="Sale Gap - Difference between product list price and invoice unit price")
    turnover = fields.Float(readonly=True,
        help="Sum of Multiplication of Invoice price and quantity of Customer Invoices in invoice's company currency")
    sale_expected = fields.Float(string='Expected Sale', readonly=True,
        help="Sum of Multiplication of Sale Catalog price and quantity of Customer Invoices")
    purchase_num_invoiced = fields.Float(string='#Products Purchased', readonly=True,
        help="Sum of Products Quantity in Vendor Bills")
    purchase_avg_price = fields.Float(string='Avg. Cost Price', readonly=True,
        help="Avg. Price in Vendor Bills ")
    purchase_gap = fields.Float(readonly=True,
        help="Purchase Gap - Difference between product cost price and invoice unit price")
    total_cost = fields.Float(readonly=True,
        help="Sum of Multiplication of Invoice price and quantity of Supplier Invoices in invoice's company currency")
    normal_cost = fields.Float(readonly=True,
        help="Sum of Multiplication of Cost price and quantity of Vendor Bills")
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    standard_price = fields.Float(string='Cost Price', readonly=True)
    list_price = fields.Float(string='Sale Price', readonly=True)


    def init(self, cr):
        drop_view_if_exists(cr, 'report_product_margin')
        cr.execute("""
            CREATE OR REPLACE VIEW report_product_margin AS (
            WITH invoice(id, invoice_type, product_id, list_price, standard_price, invoice_total, total_qty, expected_total, sub_total) AS (
                SELECT
                    l.id AS id,
                    i.type AS invoice_type,
                    l.product_id AS product_id,
                    min(pt.list_price) AS list_price,
                    min(ip.value_float) AS standard_price,
                    sum(l.price_unit * l.quantity) AS invoice_total,
                    sum(l.quantity) AS total_qty,
                    sum(l.quantity * pt.list_price) AS expected_total,
                    sum(l.price_subtotal_signed) AS sub_total
                FROM account_invoice_line l
                    LEFT JOIN account_invoice i ON l.invoice_id = i.id
                    LEFT JOIN product_product product ON product.id = l.product_id
                    LEFT JOIN product_template pt ON pt.id = product.product_tmpl_id
                    LEFT JOIN ir_property ip ON (ip.name='standard_price' AND ip.res_id=CONCAT('product.product,',product.id))
                GROUP BY l.id, l.product_id, i.type
                )
                SELECT min(line.id) AS id,
                    i.state AS invoice_state,
                    i.date_invoice AS invoice_date,
                    i.currency_id AS currency_id,
                    product.id AS product_id,
                    product.product_tmpl_id AS product_tmpl_id,
                    min(customer_invoice.list_price) AS list_price,
                    sum(customer_invoice.sub_total) AS turnover,
                    sum(customer_invoice.invoice_total) / sum(NULLIF(customer_invoice.total_qty, 0)) AS sale_avg_price,
                    sum(customer_invoice.total_qty) as sale_num_invoiced,
                    sum(customer_invoice.expected_total) AS sale_expected,
                    sum(customer_invoice.expected_total) - sum(customer_invoice.sub_total) AS sales_gap,
                    min(supplier_invoice.standard_price) AS standard_price,
                    sum(supplier_invoice.invoice_total) / sum(NULLIF(supplier_invoice.total_qty, 0)) AS purchase_avg_price,
                    sum(supplier_invoice.total_qty) AS purchase_num_invoiced,
                    sum(supplier_invoice.total_qty * supplier_invoice.standard_price) AS normal_cost,
                    sum(supplier_invoice.sub_total) AS total_cost,
                    sum(supplier_invoice.total_qty * supplier_invoice.standard_price) - sum(supplier_invoice.sub_total) AS purchase_gap,
                    CASE WHEN sum(customer_invoice.sub_total) IS NULL THEN 0.00 ELSE sum(customer_invoice.sub_total) END - 
                        CASE WHEN sum(supplier_invoice.sub_total) IS NULL THEN 0.00 ELSE sum(supplier_invoice.sub_total) END AS total_margin,
                    CASE WHEN sum(customer_invoice.expected_total) IS NULL THEN 0.00 ELSE sum(customer_invoice.expected_total) END - 
                        CASE WHEN sum(supplier_invoice.total_qty) IS NULL THEN 0.00 ELSE sum(supplier_invoice.total_qty * supplier_invoice.standard_price) END AS expected_margin
                FROM account_invoice_line line
                LEFT JOIN account_invoice i ON i.id = line.invoice_id
                LEFT JOIN product_product product ON product.id = line.product_id
                LEFT JOIN invoice customer_invoice ON customer_invoice.invoice_type in ('out_invoice','in_refund') AND
                    customer_invoice.product_id = product.id and line.id = customer_invoice.id
                LEFT JOIN invoice supplier_invoice ON supplier_invoice.invoice_type in ('in_invoice', 'out_refund') AND
                    supplier_invoice.product_id = product.id and line.id = supplier_invoice.id
                WHERE i.state in ('open', 'paid', 'proforma', 'proforma2')
                GROUP BY i.state, i.date_invoice, product.id, i.currency_id
            )
            """)
