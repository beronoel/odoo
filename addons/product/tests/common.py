# -*- coding: utf-8 -*-

from odoo.tests import common


class TestProductCommon(common.SavepointCase):

    @classmethod
    def setUpClass(cls):
        super(TestProductCommon, cls).setUpClass()

        # Customer related data
        cls.partner_1 = cls.env['res.partner'].create({
            'name': 'Julia Agrolait',
            'email': 'julia@agrolait.example.com',
        })

        # Product environment related data
        Uom = cls.env['product.uom']
        categ_unit = cls.env.ref('product.product_uom_categ_unit')
        weight_unit = cls.env.ref('product.product_uom_categ_kgm')
        cls.uom_unit = Uom.create({
            'name': 'BaseUnit',
            'category_id': categ_unit.id,
            'factor_inv': 1.0,
            'factor': 1.0,
            'uom_type': 'reference',
            'rounding': 0.000001})
        cls.uom_dozen = Uom.create({
            'name': 'DozenUnit',
            'category_id': categ_unit.id,
            'factor_inv': 12.0,
            'factor': 0.001,
            'uom_type': 'bigger',
            'rounding': 0.001})
        cls.uom_dunit = Uom.create({
            'name': 'DeciUnit',
            'category_id': categ_unit.id,
            'factor_inv': 0.1,
            'factor': 10.0,
            'uom_type': 'smaller',
            'rounding': 0.001})
        cls.uom_weight = Uom.create({
            'name': 'TestWeight',
            'category_id': weight_unit.id,
            'factor_inv': 1.0,
            'factor': 1.0,
            'uom_type': 'reference',
            'rounding': 0.000001
        })
        Product = cls.env['product.product']
        cls.product_1 = Product.create({
            'name': 'Table (uom_unit)',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id})
        cls.product_2 = Product.create({
            'name': 'Batten (uom_unit)',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id})
        cls.product_3 = Product.create({
            'name': 'Table Legs (uom_unit)',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id})
        cls.product_4 = Product.create({
            'name': 'Shelf Bracket (uom_unit)',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id})
        cls.product_5 = Product.create({
            'name': 'Rafter (uom_dunit)',
            'uom_id': cls.uom_dunit.id,
            'uom_po_id': cls.uom_dunit.id})
