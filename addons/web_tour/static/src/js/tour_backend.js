odoo.define('web_tour.tour', function(require) {
"use strict";

var Tour = require('web_tour.Tour');

Tour.include({
    init: function() {
        this._super();
        if (document.body) {
            this.observe();
        } else {
            document.addEventListener("DOMContentLoaded", this.observe.bind(this));
        }
    },
    observe: function () {
        var check_tooltip = _.throttle(this.check_for_tooltip.bind(this), 500, {leading: false});
        var observer = new MutationObserver(check_tooltip);
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            // characterData: true
        });
    }
});

return new Tour();

});
