# -*- coding: utf-8 -*-
from openerp.addons.web import http
from openerp.http import request


class Web_Editor_Backend(http.Controller):
    @http.route('/web_editor_backend/get_all_fields', type='json', auth='user')
    def get_all_fields(self, model):
        """ get_all_fields(model)

        Return the definition of each field.

        The returned value is a dictionary (indiced by field name) of
        dictionaries. The _inherits'd fields are included. The string, help,
        and selection attributes are translated.
        """
        fields = request.env[model]._fields

        res = {}
        for fname, field in fields.iteritems():
            res[fname] = field.get_description(request.env)
            print field.groups
            print res[fname]

        return res
