odoo.define('website.tour.cancel', function (require) {
    "use strict";
    require('web.Tour').autoRunning = false;
});

odoo.define('website.tour', function (require) {
    "use strict";

    var Tour = require('web.Tour');
    var tour = require('web_tour.tour');
    var website = require('website.website');
    var base = require('web_editor.base');

    website.TopBar.include({
        tours: [],
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).done(function () {
                var $menu = self.$('#help-menu');
                _.each(tour.tours, function (tour) {
                    // if (tour.mode === "test") { FIXME
                    //     return;
                    // }
                    var $menuItem = $($.parseHTML("<li><a href=\"#\">" + tour.id + "</a></li>"));
                    // $menuItem.click(function () { FIXME
                    //     tour.run(tour.id);
                    // });
                    $menu.append($menuItem);
                });
            });
        }
    });

    base.ready().then(Tour.running);
});
