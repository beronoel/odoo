odoo.define('web_tour.Tour', function(require) {
"use strict";

var core = require('web.core');
var Tip = require('web_tour.Tip');

function getCurrentStep(name) {
    var key = 'tour_' + name + '_step';
    return parseInt(window.localStorage.getItem(key)) || 0;
}


return core.Class.extend({
    init: function() {
        this.active_tooltips = {};
        this.tours = {};
    },
    register: function() {
        var args = Array.prototype.slice.call(arguments);
        var last_arg = args[args.length - 1];
        var name = args[0];
        var options = args.length === 2 ? {} : args[1];
        var steps = last_arg instanceof Array ? last_arg : [last_arg];
        var tour = {
            name: name,
            current_step: getCurrentStep(name),
            steps: steps,
            url: options.url,
        };
        this.tours[name] = tour;
        this.active_tooltips[name] = steps[tour.current_step];
    },
     check_for_tooltip: function() {
        var self = this;
        _.each(this.active_tooltips, function (tip, tour) {
            var $trigger = $(tip.trigger).filter(':visible').first();
            var extra_trigger = tip.extra_trigger ? $(tip.extra_trigger).filter(':visible').length : true;
            var triggered = $trigger.length && extra_trigger;
            if (triggered && !tip.widget) {
                self.activate_tip(tip, tour, $trigger);
            }
            if (!triggered && tip.widget) {
                self.unactivate_tip(tip);
            }
        });
    },
    activate_tip: function(tip, tour, $anchor) {
        tip.widget = new Tip(this, $anchor, tip);
        tip.widget.appendTo(document.body);
        tip.widget.on('tip_consumed', this, this.consume_tip.bind(this, tip, tour));
    },
    unactivate_tip: function(tip) {
        tip.widget.destroy();
        delete tip.widget;
    },
    consume_tip: function(tip, tour_name) {
        delete this.active_tooltips[tour_name];
        var tour = this.tours[tour_name];
        if (tour.current_step < tour.steps.length - 1) {
            this.unactivate_tip(tip);
            tour.current_step = tour.current_step + 1;
            this.active_tooltips[tour_name] = tour.steps[tour.current_step];
            // to do: update localstorage
        } else {
            console.log('tour completed', tour);
            // to do: contact server, consume tour, remove from localstorage
        }
    },
});

});
