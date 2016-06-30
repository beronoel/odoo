odoo.define('website_crm.tour', function(require) {
    'use strict';

    var base = require('web_editor.base');
    var core = require('web.core');
    var tour = require('web_tour.tour');

    var _t = core._t;

    base.ready().done(function () { // FIXME mode test
        tour.register("website_crm_tour", {
            skip_enabled: true,
            url: "/page/contactus"
        }, [{
            trigger: "input[name=contact_name]",
            content: _t("Complete name"),
            sampleText: "John Smith", // FIXME
        }, {
            trigger: "input[name=phone]",
            content: _t("Complete phone number"),
            sampleText: "118.218" // FIXME
        }, {
            trigger: "input[name=email_from]",
            content: _t("Complete Email"),
            sampleText: "john@smith.com" // FIXME
        }, {
            trigger: "input[name=partner_name]",
            content: _t("Complete Company"),
            sampleText: "Odoo S.A." // FIXME
        }, {
            trigger: "input[name=name]",
            content: _t("Complete Subject"),
            sampleText: "Useless message" // FIXME
        }, {
            trigger: "textarea[name=description]",
            content: _t("Complete Subject"),
            sampleText: "### TOUR DATA ###" // FIXME
        }, {
            trigger: ".o_website_form_send",
            content: _t("Send the form"),
        }, {
            waitFor: "#wrap:has(h1:contains('Thanks')):has(div.alert-success)",
            content: _t("Check we were redirected to the success page"),
        }]);
    });
});
