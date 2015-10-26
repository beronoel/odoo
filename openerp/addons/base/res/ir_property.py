# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from operator import itemgetter

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# -------------------------------------------------------------------------
# Properties
# -------------------------------------------------------------------------

TYPE2FIELD = {
    'char': 'value_text',
    'float': 'value_float',
    'boolean': 'value_integer',
    'integer': 'value_integer',
    'text': 'value_text',
    'binary': 'value_binary',
    'many2one': 'value_reference',
    'date': 'value_datetime',
    'datetime': 'value_datetime',
    'selection': 'value_text',
}


class IrProperty(models.Model):
    _name = 'ir.property'

    name = fields.Char(index=True)
    res_id = fields.Char(string='Resource',
                         help="If not set, acts as a default value for new resources",
                         index=True)
    company_id = fields.Many2one('res.company', string='Company', index=True)
    fields_id = fields.Many2one('ir.model.fields', string='Field',
                                ondelete='cascade', required=True, index=True)
    value_float = fields.Float(string='Value')
    value_integer = fields.Integer(string='Value')
    value_text = fields.Text(string='Value')  # will contain (char, text)
    value_binary = fields.Binary(string='Value')
    value_reference = fields.Char(string='Value')
    value_datetime = fields.Datetime(string='Value')
    type = fields.Selection([('char', 'Char'),
                             ('float', 'Float'),
                             ('boolean', 'Boolean'),
                             ('integer', 'Integer'),
                             ('text', 'Text'),
                             ('binary', 'Binary'),
                             ('many2one', 'Many2One'),
                             ('date', 'Date'),
                             ('datetime', 'DateTime'),
                             ('selection', 'Selection'),
                             ],
                            required=True,
                            default='many2one',
                            index=True)

    def _update_values(self, values):
        value = values.pop('value', None)
        if not value:
            return values

        type_ = values.get('type')
        if not type_:
            if self.ids:
                type_ = self.type
            else:
                type_ = self._defaults['type']

        field = TYPE2FIELD.get(type_)
        if not field:
            raise UserError(_('Invalid type'))

        if field == 'value_reference':
            if isinstance(value, models.BaseModel):
                value = '%s,%d' % (value._name, value.id)
            elif isinstance(value, (int, long)):
                field_id = values.get('fields_id')
                if not field_id:
                    if not self:
                        raise ValueError()
                    field_id = self.fields_id
                else:
                    field_id = self.env['ir.model.fields'].browse(field_id)

                value = '%s,%d' % (field_id.relation, value)

        values[field] = value
        return values

    @api.multi
    def write(self, values):
        return super(IrProperty, self).write(self._update_values(values))

    @api.model
    def create(self, values):
        return super(IrProperty, self).create(self._update_values(values))

    @api.v7
    def get_by_record(self, cr, uid, record, context=None):
        prop = self.browse(cr, uid, record.id, context)
        return prop.get_by_record()

    @api.v8
    def get_by_record(self):
        self.ensure_one()
        if self.type in ('char', 'text', 'selection'):
            return self.value_text
        elif self.type == 'float':
            return self.value_float
        elif self.type == 'boolean':
            return bool(self.value_integer)
        elif self.type == 'integer':
            return self.value_integer
        elif self.type == 'binary':
            return self.value_binary
        elif self.type == 'many2one':
            if not self.value_reference:
                return False
            model, resource_id = self.value_reference.split(',')
            value = self.env[model].browse(int(resource_id))
            return value.exists()
        elif self.type == 'datetime':
            return self.value_datetime
        elif self.type == 'date':
            if not self.value_datetime:
                return False
            return fields.Date.from_string(self.value_datetime)
        return False

    @api.model
    def get(self, name, model, res_id=False):
        domain = self._get_domain(name, model)
        if domain is not None:
            domain = [('res_id', '=', res_id)] + domain
            #make the search with company_id asc to make sure that properties specific to a company are given first
            prop = self.search(domain, limit=1, order='company_id')
            if not prop:
                return False
            return prop.get_by_record()
        return False

    def _get_domain(self, prop_name, model):
        field = self.env['ir.model.fields'].search([('name', '=', prop_name), ('model', '=', model)], limit=1)
        if not field:
            return None

        cid = self.env.context.get('force_company', self.env['res.company']._company_default_get().id)
        return [('fields_id', '=', field.id), ('company_id', 'in', [cid, False])]

    @api.model
    def get_multi(self, name, model, ids):
        """ Read the property field `name` for the records of model `model` with
            the given `ids`, and return a dictionary mapping `ids` to their
            corresponding value.
        """
        if not ids: return {}

        domain = self._get_domain(name, model)
        if domain is None:
            return dict.fromkeys(ids, False)

        # retrieve the values for the given ids and the default value, too
        refs = {('%s,%s' % (model, id)): id for id in ids}
        refs[False] = False
        domain += [('res_id', 'in', list(refs))]

        # note: order by 'company_id asc' will return non-null values first
        props = self.search(domain, order='company_id')
        result = {}
        for prop in props:
            # for a given res_id, take the first property only
            res_id = refs.pop(prop.res_id, None)
            if res_id is not None:
                result[res_id] = prop.get_by_record()

        # set the default value to the ids that are not in result
        default_value = result.pop(False, False)
        for id in ids:
            result.setdefault(id, default_value)

        return result

    @api.model
    def set_multi(self, name, model, values):
        """ Assign the property field `name` for the records of model `model`
            with `values` (dictionary mapping record ids to their value).
        """
        def clean(value):
            return value.id if isinstance(value, models.BaseModel) else value

        if not values:
            return

        domain = self._get_domain(name, model)
        if domain is None:
            raise Exception()

        # retrieve the default value for the field
        default_value = clean(self.get(name, model))

        # retrieve the properties corresponding to the given record ids
        field_id = self.env['ir.model.fields'].search([('name', '=', name), ('model', '=', model)]).id
        company_id = self.env.context.get('force_company', self.env['res.company']._company_default_get().id)
        refs = {('%s,%s' % (model, id)): id for id in values}
        props = self.search([
            ('fields_id', '=', field_id),
            ('company_id', '=', company_id),
            ('res_id', 'in', list(refs)),
        ])

        # modify existing properties
        for prop in props:
            value = clean(values[refs.pop(prop.res_id)])
            if value == default_value:
                prop.unlink()
            elif value != clean(prop.get_by_record()):
                prop.write({'value': value})

        # create new properties for records that do not have one yet
        for ref, id in refs.iteritems():
            value = clean(values[id])
            if value != default_value:
                self.create({
                    'fields_id': field_id,
                    'company_id': company_id,
                    'res_id': ref,
                    'name': name,
                    'value': value,
                    'type': self.env[model]._fields[name].type,
                })

    @api.model
    def search_multi(self, name, model, operator, value):
        """ Return a domain for the records that match the given condition. """
        default_matches = False
        include_zero = False

        field = self.env[model]._fields[name]
        if field.type == 'many2one':
            comodel = field.comodel_name

            def makeref(value):
                return value and '%s,%s' % (comodel, value)
            if operator == "=":
                value = makeref(value)
                # if searching properties not set, search those not in those set
                if value is False:
                    default_matches = True
            elif operator in ('!=', '<=', '<', '>', '>='):
                value = makeref(value)
            elif operator in ('in', 'not in'):
                value = map(makeref, value)
            elif operator in ('=like', '=ilike', 'like', 'not like', 'ilike', 'not ilike'):
                # most probably inefficient... but correct
                target_names = self.env[comodel].name_search(value, operator=operator, limit=None)
                target_ids = map(itemgetter(0), target_names)
                operator, value = 'in', map(makeref, target_ids)
        elif field.type in ('integer', 'float'):
            # No record is created in ir.property if the field's type is float or integer with a value
            # equal to 0. Then to match with the records that are linked to a property field equal to 0,
            # the negation of the operator must be taken  to compute the goods and the domain returned
            # to match the searched records is just the opposite.
            if value == 0 and operator == '=':
                operator = '!='
                include_zero = True
            elif value <= 0 and operator == '>=':
                operator = '<'
                include_zero = True
            elif value <= 0 and operator == '>':
                operator = '<='
                include_zero = True
            elif value >= 0 and operator == '<=':
                operator = '>'
                include_zero = True
            elif value >= 0 and operator == '<':
                operator = '>='
                include_zero = True

        # retrieve the properties that match the condition
        domain = self._get_domain(name, model)
        if domain is None:
            raise Exception()
        props = self.search(domain + [(TYPE2FIELD[field.type], operator, value)])

        # retrieve the records corresponding to the properties that match
        good_ids = []
        for prop in props:
            if prop.res_id:
                res_model, res_id = prop.res_id.split(',')
                good_ids.append(int(res_id))
            else:
                default_matches = True

        if include_zero:
            return [('id', 'not in', good_ids)]
        elif default_matches:
            # exclude all records with a property that does not match
            all_ids = []
            props = self.search(domain + [('res_id', '!=', False)])
            for prop in props:
                res_model, res_id = prop.res_id.split(',')
                all_ids.append(int(res_id))
            bad_ids = list(set(all_ids) - set(good_ids))
            return [('id', 'not in', bad_ids)]
        else:
            return [('id', 'in', good_ids)]
