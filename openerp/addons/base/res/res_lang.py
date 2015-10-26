# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import locale
import logging
from locale import localeconv
from operator import itemgetter
import re

from odoo import api, fields, models, SUPERUSER_ID, tools, _
from odoo.tools.safe_eval import safe_eval as eval
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Lang(models.Model):
    _name = "res.lang"
    _description = "Languages"
    _order = "active desc,name"

    _disallowed_datetime_patterns = tools.DATETIME_FORMATS_MAP.keys()
    _disallowed_datetime_patterns.remove('%y')  # this one is in fact allowed, just not good practice

    @api.model
    def install_lang(self):
        """

        This method is called from openerp/addons/base/base_data.xml to load
        some language and set it as the default for every partners. The
        language is set via tools.config by the RPC 'create' method on the
        'db' object. This is a fragile solution and something else should be
        found.

        """
        IrValues = self.env['ir.values']
        # config['load_language'] is a comma-separated list or None
        lang = (tools.config['load_language'] or 'en_US').split(',')[0]
        lang_rec = self.search([('code', '=', lang)])
        if not lang_rec:
            self.load_lang(lang)
        default_value = IrValues.get('default', False, ['res.partner'])
        if not default_value:
            IrValues.set('default', False, 'lang', ['res.partner'], lang)
        return True

    def load_lang(self, cr, uid, lang, lang_name=None):
        """ Create the given language if necessary, and make it active. """
        # if the language exists, simply make it active
        lang_ids = self.search(cr, uid, [('code', '=', lang)], context={'active_test': False})
        if lang_ids:
            self.write(cr, uid, lang_ids, {'active': True})
            return lang_ids[0]

        # create the language with locale information
        fail = True
        iso_lang = tools.get_iso_codes(lang)
        for ln in tools.get_locales(lang):
            try:
                locale.setlocale(locale.LC_ALL, str(ln))
                fail = False
                break
            except locale.Error:
                continue
        if fail:
            lc = locale.getdefaultlocale()[0]
            msg = 'Unable to get information for locale %s. Information from the default locale (%s) have been used.'
            _logger.warning(msg, lang, lc)

        if not lang_name:
            lang_name = lang

        def fix_xa0(s):
            """Fix badly-encoded non-breaking space Unicode character from locale.localeconv(),
               coercing to utf-8, as some platform seem to output localeconv() in their system
               encoding, e.g. Windows-1252"""
            if s == '\xa0':
                return '\xc2\xa0'
            return s

        def fix_datetime_format(format):
            """Python's strftime supports only the format directives
               that are available on the platform's libc, so in order to
               be 100% cross-platform we map to the directives required by
               the C standard (1989 version), always available on platforms
               with a C standard implementation."""
            # For some locales, nl_langinfo returns a D_FMT/T_FMT that contains
            # unsupported '%-' patterns, e.g. for cs_CZ
            format = format.replace('%-', '%')
            for pattern, replacement in tools.DATETIME_FORMATS_MAP.iteritems():
                format = format.replace(pattern, replacement)
            return str(format)

        lang_info = {
            'code': lang,
            'iso_code': iso_lang,
            'name': lang_name,
            'active': True,
            'translatable': True,
            'date_format': fix_datetime_format(locale.nl_langinfo(locale.D_FMT)),
            'time_format': fix_datetime_format(locale.nl_langinfo(locale.T_FMT)),
            'decimal_point': fix_xa0(str(locale.localeconv()['decimal_point'])),
            'thousands_sep': fix_xa0(str(locale.localeconv()['thousands_sep'])),
        }
        lang_id = False
        try:
            lang_id = self.create(cr, uid, lang_info)
        finally:
            tools.resetlocale()
        return lang_id

    def _register_hook(self, cr):
        # check that there is at least one active language
        if not self.search_count(cr, SUPERUSER_ID, []):
            _logger.error("No language is active.")

    def _check_active(self, cr, uid, ids, context=None):
        # do not check during installation
        return not self.pool.ready or bool(self.search_count(cr, uid, []))

    @api.multi
    @api.constrains('time_format', 'date_format')
    def _check_format(self):
        for lang in self:
            for pattern in self._disallowed_datetime_patterns:
                if (lang.time_format and pattern in lang.time_format) or (
                   lang.date_format and pattern in lang.date_format):
                    raise UserError(_('Invalid date/time format directive specified. Please refer to the list of allowed directives, displayed when you edit a language.'))

    @api.multi
    @api.constrains('grouping')
    def _check_grouping(self):
        for lang in self:
            if not all(isinstance(x, int) for x in eval(lang.grouping)):
                raise UserError(_('The Separator Format should be like [,n] where 0 < n :starting from Unit digit.-1 will end the separation. e.g. [3,2,-1] will represent 106500 to be 1,06,500;[1,2,-1] will represent it to be 106,50,0;[3] will represent it as 106,500. Provided ', ' as the thousand separator in each case.'))

    def _get_default_date_format(self):
        return '%m/%d/%Y'

    def _get_default_time_format(self):
        return '%H:%M:%S'

    name = fields.Char(required=True)
    code = fields.Char(string='Locale Code', size=16, required=True,
                       help='This field is used to set/get locales for user')
    iso_code = fields.Char(
        size=16, required=False,
        help='This ISO code is the name of po files to use for translations')
    translatable = fields.Boolean(default=False)
    active = fields.Boolean(default=False)
    direction = fields.Selection([('ltr', 'Left-to-Right'),
                                  ('rtl', 'Right-to-Left')], required=True,
                                 default='ltr')
    date_format = fields.Char(required=True, default=_get_default_date_format)
    time_format = fields.Char(required=True, default=_get_default_time_format)
    grouping = fields.Char(
        string='Separator Format', required=True,
        default='[]',
        help="The Separator Format should be like [,n] where 0 < n :starting from Unit digit.-1 will end the separation. e.g. [3,2,-1] will represent 106500 to be 1,06,500;[1,2,-1] will represent it to be 106,50,0;[3] will represent it as 106,500. Provided ',' as the thousand separator in each case.")
    decimal_point = fields.Char(string='Decimal Separator', required=True,
                                default='.')
    thousands_sep = fields.Char(string='Thousands Separator', default=',')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', _('The name of the language must be unique !')),
        ('code_uniq', 'unique (code)', _('The code of the language must be unique !')),
    ]

    _constraints = [
        (_check_active, "At least one language must be active.", ['active'])]

    @api.model
    @tools.ormcache('lang')
    def _lang_get(self, lang):
        langs = self.search([('code', '=', lang)], limit=1) or self.search([('code', '=', 'en_US')], limit=1) or self.search([], limit=1)
        return langs.id

    @api.model
    @tools.ormcache('lang', 'monetary')
    def _lang_data_get(self, lang, monetary=False):
        if type(lang) in (str, unicode):
            lang = self._lang_get(lang)
        conv = localeconv()
        lang_rec = self.browse(lang)
        thousands_sep = lang_rec.thousands_sep or conv[monetary and 'mon_thousands_sep' or 'thousands_sep']
        decimal_point = lang_rec.decimal_point
        grouping = lang_rec.grouping
        return grouping, thousands_sep, decimal_point

    @api.model
    @tools.ormcache()
    def get_available(self):
        """ Return the available languages as a list of (code, name) sorted by name. """
        langs = self.with_context({'active_test': False}).search([])
        return sorted([(lang.code, lang.name) for lang in langs], key=itemgetter(1))

    @api.model
    @tools.ormcache()
    def get_installed(self):
        """ Return the installed languages as a list of (code, name) sorted by name. """
        langs = self.search([])
        return sorted([(lang.code, lang.name) for lang in langs], key=itemgetter(1))

    @api.model
    def create(self, vals):
        self.clear_caches()
        return super(Lang, self).create(vals)

    @api.multi
    def write(self, vals):
        if isinstance(self.ids, (int, long)):
            self.ids = [self.ids]

        if 'code' in vals:
            for rec in self:
                if rec.code != vals['code']:
                    raise UserError(_("Language code cannot be modified."))

        if vals.get('active') == False:
            for current_id in self.ids:
                current_language = self.browse(current_id)
                if self.env['res.users'].search([('lang', '=', current_language.code)]):
                    raise UserError(_("Cannot unactivate a language that is currently used by users."))

        self.clear_caches()
        return super(Lang, self).write(vals)

    @api.multi
    def unlink(self):
        languages = self.read(['code', 'active'])
        for language in languages:
            ctx_lang = self.env.context.get('lang')
            if language['code'] == 'en_US':
                raise UserError(_("Base Language 'en_US' can not be deleted!"))
            if ctx_lang and (language['code'] == ctx_lang):
                raise UserError(
                    _("You cannot delete the language which is User's Preferred Language!"))
            if language['active']:
                raise UserError(_("You cannot delete the language which is Active!\nPlease de-activate the language first."))

            irtranslation = self.env['ir.translation']
            translations = irtranslation.search([('lang', '=', language['code'])])
            translations.unlink()
        self.clear_caches()
        return super(Lang, self).unlink()

    #
    # IDS: can be a list of IDS or a list of XML_IDS
    #
    def format(self, cr, uid, ids, percent, value, grouping=False, monetary=False, context=None):
        """ Format() will return the language-specific output for float values"""
        if percent[0] != '%':
            raise ValueError("format() must be given exactly one %char format specifier")

        formatted = percent % value

        # floats and decimal ints need special action!
        if grouping:
            lang_grouping, thousands_sep, decimal_point = \
                self._lang_data_get(cr, uid, ids[0], monetary)
            eval_lang_grouping = eval(lang_grouping)

            if percent[-1] in 'eEfFgG':
                parts = formatted.split('.')
                parts[0], _ = intersperse(parts[0], eval_lang_grouping, thousands_sep)

                formatted = decimal_point.join(parts)

            elif percent[-1] in 'diu':
                formatted = intersperse(formatted, eval_lang_grouping, thousands_sep)[0]

        return formatted
#    import re, operator
#    _percent_re = re.compile(r'%(?:\((?P<key>.*?)\))?'
#                             r'(?P<modifiers>[-#0-9 +*.hlL]*?)[eEfFgGdiouxXcrs%]')


def split(l, counts):
    """

    >>> split("hello world", [])
    ['hello world']
    >>> split("hello world", [1])
    ['h', 'ello world']
    >>> split("hello world", [2])
    ['he', 'llo world']
    >>> split("hello world", [2,3])
    ['he', 'llo', ' world']
    >>> split("hello world", [2,3,0])
    ['he', 'llo', ' wo', 'rld']
    >>> split("hello world", [2,-1,3])
    ['he', 'llo world']

    """
    res = []
    saved_count = len(l)  # count to use when encoutering a zero
    for count in counts:
        if not l:
            break
        if count == -1:
            break
        if count == 0:
            while l:
                res.append(l[:saved_count])
                l = l[saved_count:]
            break
        res.append(l[:count])
        l = l[count:]
        saved_count = count
    if l:
        res.append(l)
    return res

intersperse_pat = re.compile('([^0-9]*)([^ ]*)(.*)')


def intersperse(string, counts, separator=''):
    """

    See the asserts below for examples.

    """
    left, rest, right = intersperse_pat.match(string).groups()

    def reverse(s):
        return s[::-1]
    splits = split(reverse(rest), counts)
    res = separator.join(map(reverse, reverse(splits)))
    return left + res + right, len(splits) > 0 and len(splits) - 1 or 0
