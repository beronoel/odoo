# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tools import convert_file
from odoo.tests import common
from odoo.modules.module import get_module_resource

class TestMargin(common.TransactionCase):

    def _load(self, module, *args):
        convert_file(self.cr, 'product_margin',
                           get_module_resource(module, *args),
                           {}, 'init', False, 'test', self.registry._assertion_report)

    def setUp(self):

        super(TestMargin, self).setUp()

        self._load('account', 'test', 'account_minimal_test.xml')

        self.AccountInvoice = self.env['account.invoice']
        self.ProductMargin = self.env['report.product.margin']
        self.partner2_id = self.ref('base.res_partner_2')
        self.ipad = self.env.ref('product.product_product_6')
        self.company = self.env.ref('base.main_company')
        self.company.write({'currency_id': self.ref("base.USD")})
        self.receivable_id = self.ref('product_margin.a_recv')
        self.payable_id = self.ref('product_margin.a_pay')
        self.revenue_id = self.ref('product_margin.a_sale')
        self.expense_id = self.ref('product_margin.a_expense')

    def test_00_product_margin(self):
        "Create customer and supplier invoice for test a margin on ipad product"

        # Create customer Invoice 1
        self.customer_invoice_0 = self.AccountInvoice.create(dict(
            name="Test Customer Invoice",
            reference_type="none",
            type='out_invoice',
            partner_id=self.partner2_id,
            account_id=self.receivable_id,
            invoice_line_ids=
            [(0, 0, {
                'product_id': self.ipad.id,
                'quantity': 1,
                'account_id': self.revenue_id,
                'name': 'Test customer product',
                'price_unit': self.ipad.list_price,
            })]
        ))

        # Validate customer invoice
        self.customer_invoice_0.signal_workflow('invoice_open')
        # Search a product margin of 'ipad' product
        margin = self.ProductMargin.search([('product_id', 'in', [self.ipad.id])])
        # Test total margin on product
        self.assertEquals(margin.total_margin, 320.00, 'Wrong value of total margin')

        # Create supplier Invoice 1
        self.supplier_invoice_0 = self.AccountInvoice.create(dict(
            name="Test Supplier Invoice",
            reference_type="none",
            type='in_invoice',
            partner_id=self.partner2_id,
            account_id=self.payable_id,
            invoice_line_ids=
            [(0, 0, {
                'product_id': self.ipad.id,
                'quantity': 1,
                'account_id': self.expense_id,
                'name': 'Test supplier product',
                'price_unit': self.ipad.standard_price,
            })]
        ))
        # Validate supplier invoice
        self.supplier_invoice_0.signal_workflow('invoice_open')

        # Test total margin on product
        self.assertEquals(margin.total_margin, -480.00, 'Wrong value of total margin')

        # Create customer Invoice 2 with change price unit 275 on invoice line
        self.customer_invoice_1 = self.AccountInvoice.create(dict(
            name="Test Customer Invoice",
            reference_type="none",
            type='out_invoice',
            partner_id=self.partner2_id,
            account_id=self.receivable_id,
            invoice_line_ids=
            [(0, 0, {
                'product_id': self.ipad.id,
                'quantity': 1.0,
                'account_id': self.revenue_id,
                'name': 'Test customer product',
                'price_unit': 275,
            })]
        ))
        # Validate customer invoice
        self.customer_invoice_1.signal_workflow('invoice_open')
        # Test product margin on product
        self.assertEquals(margin.total_margin, -205.00, 'Wrong value of total margin')

        # Create supplier Invoice 2 with change standard 750 on invoice line
        self.supplier_invoice_1 = self.AccountInvoice.create(dict(
            name="Test Supplier Invoice",
            reference_type="none",
            type='in_invoice',
            partner_id=self.partner2_id,
            account_id=self.payable_id,
            invoice_line_ids=
            [(0, 0, {
                'product_id': self.ipad.id,
                'quantity': 1.0,
                'account_id': self.expense_id,
                'name': 'Test suppler product',
                'price_unit': 750,
            })]
        ))
        # Validate supplier invoice
        self.supplier_invoice_1.signal_workflow('invoice_open')

        # Test all function of product margin
        self.assertEquals(margin.total_margin, -955.00, 'Wrong value of total margin')
        self.assertEquals(margin.expected_margin, -960.00, 'Wrong value of expected margin')
        self.assertEquals(margin.turnover, 595.00, 'Wrong value of turnover')
        self.assertEquals(margin.total_cost, 1550.00, 'Wrong value of total cost')
        self.assertEquals(margin.sales_gap, 45.00, 'Wrong value of sales gap')
        self.assertEquals(margin.purchase_gap, 50.00, 'Wrong value of purchase gap')
        self.assertEquals(margin.sale_avg_price, 297.50, 'Wrong value of sale average')
        self.assertEquals(margin.purchase_avg_price, 775.00, 'Wrong purchase average')
        self.assertEquals(margin.sale_expected, 640.00, 'Wrong value of sale expected')
        self.assertEquals(margin.normal_cost, 1600.00, 'Wrong value of purchase expected')


        # Create customer Invoice for currency test
        self.customer_invoice_2 = self.AccountInvoice.create(dict(
            name="Test Customer Invoice",
            reference_type="none",
            type='out_invoice',
            partner_id=self.partner2_id,
            company_id = self.company.id,
            currency_id = self.ref('base.INR'),
            account_id=self.receivable_id,
            invoice_line_ids=
            [(0, 0, {
                'product_id': self.ipad.id,
                'quantity': 1.0,
                'account_id': self.revenue_id,
                'name': 'Test customer product',
                'price_unit': self.ipad.list_price,
            })]
        ))
        # Validate customer invoice
        self.customer_invoice_2.signal_workflow('invoice_open')

        # Search a product margin of 'ipad' product
        total_margin = 0.00
        turnover = 0.00
        for margin in self.ProductMargin.search([('product_id', 'in', [self.ipad.id])]):
            total_margin += margin.total_margin
            turnover += margin.turnover

        # Test total margin with different currency rate
        self.assertEquals(total_margin, -946.84, 'Wrong value of margin with currency')
        self.assertEquals(turnover, 603.16, 'Wrong value of turnover with currency')
