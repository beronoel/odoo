odoo.define('barcode.InheritedFormWidgetButton', function (require) {
"use strict";

var core = require('web.core');
var widgets = require('web.form_widgets');
var BarcodeEvents = require('barcodes.BarcodeEvents');
var BarcodeHandlerMixin = require('barcodes.BarcodeHandlerMixin');

var _t = core._t;

// If the button has a barcode_trigger attribute, dynamically inherit
// BarcodeHandlerMixin and redefine on_barcode_scanned

var ButtonBarcodeHandlerMixin = _.extend({}, BarcodeHandlerMixin, {
    init: function(field_manager, node) {
        if (node.attrs.barcode_trigger) {
            BarcodeHandlerMixin.init.call(this, field_manager, node);
            var self = this;
            this.on_barcode_scanned = function(barcode) {
                var match = barcode.match(/O-BTN\.(.+)/);
                if (match && match[1] === self.node.attrs.barcode_trigger) {
                    if (self.$el.is(':visible') || self.$el.not('.o_form_invisible').closest('ul.dropdown-menu').length) {
                        self.on_click();
                    } else {
                        var operation = self.node.attrs.barcode_trigger;
                        return self.do_warn(_t("Operation Error"), _.str.sprintf(_t("Could not perform operation %s due to button/link not visible on page."), _.str.capitalize(operation)));
                    }
                }
            };
        } else {
            this._super(field_manager, node);
        }
    },
});

BarcodeEvents.ReservedBarcodePrefixes.push('O-BTN');

widgets.WidgetButton.include(ButtonBarcodeHandlerMixin);

});
