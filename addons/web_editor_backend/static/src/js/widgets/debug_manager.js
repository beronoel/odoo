odoo.define('web_editor_backend.DebugManager', function (require) {
"use strict";

var core = require('web.core');
var DebugManager = require('web.DebugManager');
var Model = require('web.DataModel');
var Dialog = require('web.Dialog');
var session = require('web.session');

var QWeb = core.qweb;
var _t = core._t;

if (!core.debug) {
    return;
}

function dialog(template, fields, view_fields, missing_fields) {
    return $(QWeb.render(template, {
            'fields': fields,
            'view_fields': view_fields,
            'missing_fields': missing_fields,
        })).on('change', 'select[name="missing_field"], select[name="view_field"]', function (event) {
            var $select = $(event.target);
            var $desc = $("<table/>");
            var field = fields[$select.val()];
            var keys = _.keys(field);
            keys.sort();
            _.each(keys, function (key) {
                var val = _.isObject(field[key]) ? JSON.stringify(field[key]) : field[key];
                var css = {'padding-left': '10px'};
                if (key === "name" || key === "string") {
                    css['font-weight'] = 700;
                }
                $desc.append($("<tr><td><label></label></td><td></td></tr>").find('label').text(key).end().find('td:last').text(val).css(css).end());
            });
            $select.closest('table').find('td.oe_form_group_cell:last').html($desc);
        });
}

return DebugManager.include({
    get_fields_informations: function () {
        var self = this;
        var view = this.active_view.controller.fields_view;

        return this.dataset.call('fields_get', [false, {}]).then(function (fields) {

            function order (a, b) {
                return fields[a].string.toUpperCase() < fields[b].string.toUpperCase() ? -1 : 1;
            }

            var view_fields = _.keys(view.fields);
            view_fields.sort(order);

            var missing_fields = _.difference(_.keys(fields), view_fields);
            missing_fields.sort(order);

            _.each(fields, function (v, k) {
                v['name'] = k;
            });

            return self.get_added_fields().then(function (views) {
                var added_fields = _.pluck(_.flatten(_.pluck(views, 'fields')), 'name');
                added_fields.sort(order);

                return self.fields_informations = {
                    'view': view,
                    'views': views,
                    'fields': fields,
                    'included': view_fields,
                    'missing': missing_fields,
                    'added': added_fields,
                };
            });
        });
    },
    get_added_fields: function() {
        var view = this.active_view.controller.fields_view;
        return new Model('ir.ui.view').call("search_read", [[['inherit_id', '=', view.view_id], ['key', 'like', 'web_editor_backend.%']], []]).then(function (views) {
            _.each(views, function (view) {
                view.fields = [];

                $(view.arch).find('field[name]:not([position])').each(function () {
                    var field = {'web_editor_backend_type' : 'new'};
                    _.each(this.attributes, function (v) {
                        field[v.name] = v.value;
                        if (/true|1/i.test(field[v.name])) {
                            field[v.name] = true;
                        } else if (/false|0/i.test(field[v.name])) {
                            field[v.name] = false;
                        }
                    });
                    view.fields.push(field);
                });

                $(view.arch).find('field[name][position="attributes"]').each(function () {
                    var field = {
                        'web_editor_backend_type' : 'attributes',
                        'name': $(this).get('name')
                    };
                    $(this).children().each(function () {
                        field[$(this).get('name')] = $(this).html();
                    });
                    view.fields.push(field);
                });
            });
            return views;
        });
    },
    reload_view: function () {
        var self = this;
        var hash = window.location.hash;
        var params = $.deparam(window.location.hash.slice(1));
        this.view.load_view().then(function () {
            window.location.hash = '#';
            self.view_manager.do_load_state(params);
            window.location.hash = hash;
        });
    },
    add_field: function(params, evt) {
        var self = this;
        this.get_fields_informations().done(function (data) {
            var $content = dialog('WebClient.DebugAddField', data.fields, data.included, data.missing);

            new Dialog(self, {
                'title': _.str.sprintf(_t("Model %s fields"), self.dataset.model),
                '$content': $content,
                'buttons': [
                    {'text': _t('Add Field'), classes: 'btn-primary', close: true, click: function() {
                        var position = $content.find('select[name="position"]').val();
                        var field = $content.find('select[name="missing_field"]').val();
                        var ref = $content.find('select[name="view_field"]').val();
                        var name = data.view.model + ".addfield." + field;
                        var values = {
                            'key': 'web_editor_backend.' + name,
                            'name': name,
                            'type': data.view.type,
                            'model': data.view.model,
                            'inherit_id': data.view.view_id,
                            'arch': "<?xml version=\"1.0\"?>\n<data><field name='"+ref+"' position='"+position+"'><field name='"+field+"'/></field></data>",
                        };
                        new Model("ir.ui.view").call("create", [values]).then(function () {
                            self.reload_view();
                        });
                    }},

                    {'text': _t('Cancel'), close: true}
                ]
            }).open();
        });
    },
    remove_field: function(params, evt) {
        var self = this;
        this.get_fields_informations().done(function (data) {
            var $content = dialog('WebClient.DebugRemoveField', data.fields, data.added);

            new Dialog(self, {
                'title': _.str.sprintf(_t("Model %s fields"), self.dataset.model),
                '$content': $content,
                'buttons': [
                    {'text': _t('Remove Field'), classes: 'btn-primary', close: true, click: function() {
                        var field = $content.find('select[name="view_field"]').val();
                        var view = _.find(self.fields_informations.views, function (view) {
                            return _.any(view.fields, function (f) { return f.name === field;});
                        });

                        new Model("ir.ui.view").call("unlink", [view.id]).then(function () {
                            self.reload_view();
                        });
                    }},

                    {'text': _t('Cancel'), close: true}
                ]
            }).open();
        });
    },
    // get_inherit_template: function(params, evt) {
    //     var view = this.active_view.controller.fields_view;
    //     var self = this;
    //     var fields, views;

    //     var f_def = session.rpc('/web_editor_backend/get_all_fields', {'model': view.model}).then(function (res) {
    //         fields = res;
    //     });

    //     var v_def = this.get_added_fields();

    //     return $.when(f_def, v_def).then(function () {
    //         return {'fields': fields, 'views': views};
    //     });
    // },
});

});
