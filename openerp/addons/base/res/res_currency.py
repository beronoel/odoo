# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import time
import math

from openerp import api, fields, models, tools, _
from openerp.tools import float_round, float_is_zero, float_compare

CURRENCY_DISPLAY_PATTERN = re.compile(r'(\w+)\s*(?:\((.*)\))?')


class ResCurrency(models.Model):

    @api.multi
    def _get_current_rate(self):
        res = {}
        date = self.env.context.get('date') or time.strftime('%Y-%m-%d')
        company_id = self.env.context.get('company_id') or self.env['res.users']._get_company()
        for id in self.ids:
            self.env.cr.execute("""SELECT rate FROM res_currency_rate
                           WHERE currency_id = %s
                             AND name <= %s
                             AND (company_id is null
                                 OR company_id = %s)
                        ORDER BY company_id, name desc LIMIT 1""",
                                (id, date, company_id))
            if self.env.cr.rowcount:
                res[id] = self.env.cr.fetchone()[0]
            else:
                res[id] = 1
        return res

    @api.multi
    def _decimal_places(self):
        for currency in self:
            if currency.rounding > 0 and currency.rounding < 1:
                currency = int(math.ceil(math.log10(1/currency.rounding)))
            else:
                currency = 0

    @api.one
    @api.depends('rate_ids.name')
    def compute_date(self):
        self.date = self.rate_ids[:1].name

    _name = "res.currency"
    _description = "Currency"
    _order = "name"

    # Note: 'code' column was removed as of v6.0, the 'name' should now hold the ISO code.
    name = fields.Char(string='Currency', required=True, help="Currency Code (ISO 4217)")
    symbol = fields.Char(help="Currency sign, to be used when printing amounts.")
    rate = fields.Float(compute='_get_current_rate', string='Current Rate', digits=(12, 6),
                        help='The rate of the currency to the currency of rate 1.')
    rate_ids = fields.One2many('res.currency.rate', 'currency_id', string='Rates')
    rounding = fields.Float(string='Rounding Factor', digits=(12, 6), default=0.01)
    decimal_places = fields.Integer(compute='_decimal_places')
    active = fields.Boolean(default=True)
    position = fields.Selection(
        [('after', 'After Amount'),
         ('before', 'Before Amount')],
        string='Symbol Position', default='after',
        help="Determines where the currency symbol should be placed after or before the amount.")
    date = fields.Date(compute='compute_date')

    _sql_constraints = [
        ('unique_name', 'unique (name)', _('The currency code must be unique!')),
    ]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        results = super(ResCurrency, self).name_search(
            name, args, operator=operator, limit=limit)
        if not results:
            name_match = CURRENCY_DISPLAY_PATTERN.match(name)
            if name_match:
                results = super(ResCurrency, self).name_search(
                    name_match.group(1), args, operator=operator, limit=limit)
        return results

    @api.multi
    def name_get(self):
        reads = self.read(['name', 'symbol'], load='_classic_write')
        return [(x['id'], tools.ustr(x['name'])) for x in reads]

    def copy(self, cr, uid, id, default=None, context=None):
        if context is None:
            context = {}
        if not default:
            default = {}
        default.update(name=_("%s (copy)")
                       % (self.browse(cr, uid, id, context=context).name))
        return super(res_currency, self).copy(
            cr, uid, id, default=default, context=context)

    @api.v8
    def round(self, amount):
        """ Return `amount` rounded according to currency `self`. """
        return float_round(amount, precision_rounding=self.rounding)

    @api.v7
    def round(self, cr, uid, currency, amount):
        """Return ``amount`` rounded  according to ``currency``'s
           rounding rules.

           :param Record currency: currency for which we are rounding
           :param float amount: the amount to round
           :return: rounded float
        """
        return float_round(amount, precision_rounding=currency.rounding)

    @api.v8
    def compare_amounts(self, amount1, amount2):
        """ Compare `amount1` and `amount2` after rounding them according to
            `self`'s precision. An amount is considered lower/greater than
            another amount if their rounded value is different. This is not the
            same as having a non-zero difference!

            For example 1.432 and 1.431 are equal at 2 digits precision, so this
            method would return 0. However 0.006 and 0.002 are considered
            different (returns 1) because they respectively round to 0.01 and
            0.0, even though 0.006-0.002 = 0.004 which would be considered zero
            at 2 digits precision.
        """
        return float_compare(amount1, amount2, precision_rounding=self.rounding)

    @api.v7
    def compare_amounts(self, cr, uid, currency, amount1, amount2):
        """Compare ``amount1`` and ``amount2`` after rounding them according to the
           given currency's precision..
           An amount is considered lower/greater than another amount if their rounded
           value is different. This is not the same as having a non-zero difference!

           For example 1.432 and 1.431 are equal at 2 digits precision,
           so this method would return 0.
           However 0.006 and 0.002 are considered different (returns 1) because
           they respectively round to 0.01 and 0.0, even though
           0.006-0.002 = 0.004 which would be considered zero at 2 digits precision.

           :param Record currency: currency for which we are rounding
           :param float amount1: first amount to compare
           :param float amount2: second amount to compare
           :return: (resp.) -1, 0 or 1, if ``amount1`` is (resp.) lower than,
                    equal to, or greater than ``amount2``, according to
                    ``currency``'s rounding.
        """
        return float_compare(amount1, amount2, precision_rounding=currency.rounding)

    @api.v8
    def is_zero(self, amount):
        """ Return true if `amount` is small enough to be treated as zero
            according to currency `self`'s rounding rules.

            Warning: ``is_zero(amount1-amount2)`` is not always equivalent to 
            ``compare_amounts(amount1,amount2) == 0``, as the former will round
            after computing the difference, while the latter will round before,
            giving different results, e.g., 0.006 and 0.002 at 2 digits precision.
        """
        return float_is_zero(amount, precision_rounding=self.rounding)

    @api.v7
    def is_zero(self, cr, uid, currency, amount):
        """Returns true if ``amount`` is small enough to be treated as
           zero according to ``currency``'s rounding rules.

           Warning: ``is_zero(amount1-amount2)`` is not always equivalent to 
           ``compare_amounts(amount1,amount2) == 0``, as the former will round after
           computing the difference, while the latter will round before, giving
           different results for e.g. 0.006 and 0.002 at 2 digits precision.

           :param Record currency: currency for which we are rounding
           :param float amount: amount to compare with currency's zero
        """
        return float_is_zero(amount, precision_rounding=currency.rounding)

    @api.model
    def _get_conversion_rate(self, from_currency, to_currency):
        from_currency = self.browse(from_currency.id)
        to_currency = self.browse(to_currency.id)
        return to_currency.rate/from_currency.rate

    @api.model
    def _compute(self, from_currency, to_currency, from_amount, round=True):
        if (to_currency.id == from_currency.id):
            if round:
                return self.round(to_currency, from_amount)
            else:
                return from_amount
        else:
            rate = self._get_conversion_rate(from_currency, to_currency)
            if round:
                return self.round(to_currency, from_amount * rate)
            else:
                return from_amount * rate

    @api.v7
    def compute(self, cr, uid, from_currency_id, to_currency_id, from_amount,
                round=True, context=None):
        context = context or {}
        if not from_currency_id:
            from_currency_id = to_currency_id
        if not to_currency_id:
            to_currency_id = from_currency_id
        xc = self.browse(cr, uid, [from_currency_id,to_currency_id], context=context)
        from_currency = (xc[0].id == from_currency_id and xc[0]) or xc[1]
        to_currency = (xc[0].id == to_currency_id and xc[0]) or xc[1]
        return self._compute(cr, uid, from_currency, to_currency, from_amount, round, context)

    @api.v8
    def compute(self, from_amount, to_currency, round=True):
        """ Convert `from_amount` from currency `self` to `to_currency`. """
        assert self, "compute from unknown currency"
        assert to_currency, "compute to unknown currency"
        # apply conversion rate
        if self == to_currency:
            to_amount = from_amount
        else:
            to_amount = from_amount * self._get_conversion_rate(self, to_currency)
        # apply rounding
        return to_currency.round(to_amount) if round else to_amount

    @api.v7
    def get_format_currencies_js_function(self, cr, uid, context=None):
        """ Returns a string that can be used to instanciate a javascript function that formats numbers as currencies.
            That function expects the number as first parameter and the currency id as second parameter.
            If the currency id parameter is false or undefined, the company currency is used.
        """
        company_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id.currency_id.id
        function = ""
        for row in self.search_read(cr, uid, domain=[], fields=['id', 'name', 'symbol', 'decimal_places', 'position'], context=context):
            symbol = row['symbol'] or row['name']
            format_number_str = "openerp.web.format_value(arguments[0], {type: 'float', digits: [69," + str(row['decimal_places']) + "]}, 0.00)"
            if row['position'] == 'after':
                return_str = "return " + format_number_str + " + '\\xA0" + symbol + "';"
            else:
                return_str = "return '" + symbol + "\\xA0' + " + format_number_str + ";"
            function += "if (arguments[1] === " + str(row['id']) + ") { " + return_str + " }"
            if (row['id'] == company_currency_id):
                company_currency_format = return_str
        function = "if (arguments[1] === false || arguments[1] === undefined) {" + company_currency_format + " }" + function
        return function


class ResCurrencyRate(models.Model):
    _name = "res.currency.rate"
    _description = "Currency Rate"
    _order = "name desc"

    name = fields.Datetime(string='Date', required=True, index=True,
                           default=lambda *a: time.strftime('%Y-%m-%d 00:00:00'))
    rate = fields.Float(
        digits=(12, 6),
        help='The rate of the currency to the currency of rate 1')
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company')

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=80):
        if operator in ['=', '!=']:
            try:
                date_format = '%Y-%m-%d'
                if self.env.context.get('lang'):
                    langs = self.env['res.lang'].search([('code', '=', self.env.context['lang'])])
                    if langs:
                        date_format = langs.date_format
                name = time.strftime('%Y-%m-%d', time.strptime(name, date_format))
            except ValueError:
                try:
                    args.append(('rate', operator, float(name)))
                except ValueError:
                    return []
                name = ''
                operator = 'ilike'
        return super(ResCurrencyRate, self).name_search(name, args=args,
                                                        operator=operator, limit=limit)
