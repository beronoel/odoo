# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.tools import ALL_LANGUAGES, mute_logger
from openerp.tests.common import HttpCase

from lxml.etree import XMLSyntaxError
import logging
_logger = logging.getLogger(__name__)


class TranslationToolsTestCase(HttpCase):

    def test_install_language(self):
        installed_langs = []
        for lang in ALL_LANGUAGES.keys():
            lkey = [l.lower() for l in lang.split('_')]
            if len(lkey) >= 2 and lkey[0] != lkey[1] and lang not in ['pt_BR', 'zh_CN', 'el_GR']:
                # regional variation like fr_BE
                continue
            _logger.info("Install language %s" % lang)
            install = self.env['base.language.install'].create({'lang': lang})
            with mute_logger('openerp.addons.base.res.res_lang'):
                install.lang_install()
            installed_langs.append(lang)

        ir_ui_view = self.env['ir.ui.view']
        for view in ir_ui_view.search([('type', '=', 'qweb')]):
            for lang in installed_langs:
                _logger.info("Built view '%s' in %s" % (view.name, lang))
                try:
                    ir_ui_view.with_context(lang=lang).read_combined(view.id)
                except XMLSyntaxError:
                    _logger.exception("Couldn't read view %s (%s) in %s", view.name, view.id, lang)
                    _logger.warn(view.with_context(lang=lang).arch)
