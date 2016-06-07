odoo.define('web_tour.TourManager', function(require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var Tip = require('web_tour.Tip');

var _t = core._t;

function getStepKey(name) {
    return 'tour_' + name + '_step';
}
function getRunningKey() {
    return 'running_tour';
}

return core.Class.extend({
    init: function(consumed_tours) {
        this.$body = $('body');
        this.active_tooltips = {};
        this.tours = {};
        this.consumed_tours = consumed_tours;
        this.running_tour = window.localStorage.getItem(getRunningKey());
        this.TourModel = new Model('web_tour.tour');
    },
    register: function() {
        var args = Array.prototype.slice.call(arguments);
        var last_arg = args[args.length - 1];
        var name = args[0];
        if (this.tours[name]) {
            console.warn(_.str.sprintf(_t("Tour %s is already defined"), name));
            return;
        }
        var options = args.length === 2 ? {} : args[1];
        var steps = last_arg instanceof Array ? last_arg : [last_arg];
        var tour = {
            name: name,
            current_step: parseInt(window.localStorage.getItem(getStepKey(name))) || 0,
            steps: steps,
            url: options.url,
            auto: options.auto,
        };
        if (options.skip_enabled) {
            tour.skip_link = '<br/><span class="o_skip_tour">' + _t('Skip these tips.') + '</span>';
            tour.skip_handler = function (tip) {
                this._deactivate_tip(tip);
                this._consume_tour(name);
            };
        }
        this.tours[name] = tour;
        if (name === this.running_tour || (!tour.auto && !_.contains(this.consumed_tours, name))) {
            this.active_tooltips[name] = steps[tour.current_step];
        }
    },
    run: function(tour_name) {
        if (this.running_tour) {
            console.warn(_.str.sprintf(_t("Killing tour %s"), tour_name));
            this._deactivate_tip(this.active_tooltips[tour_name]);
            this._consume_tour(tour_name);
            return;
        }
        var tour = this.tours[tour_name];
        if (!tour) {
            console.warn(_.str.sprintf(_t("Unknown Tour %s"), name));
            return;
        }
        console.log(_.str.sprintf(_t("Running tour %s"), tour_name));
        window.localStorage.setItem(getRunningKey(), tour_name);
        if (tour.url) {
            window.location = tour.url;
        }
        this.running_tour = tour_name;
        this.active_tooltips[tour_name] = tour.steps[0];
        this._set_running_tour_timeout(tour_name, tour.steps[0]);
        this.update();
    },
    update: function() {
        this.in_modal = this.$body.hasClass('modal-open');
        if (this.running_tour) {
            this._check_for_tooltip(this.active_tooltips[this.running_tour], this.running_tour);
        } else {
            _.each(this.active_tooltips, this._check_for_tooltip.bind(this));
        }
    },
    _check_for_tooltip: function (tip, tour_name) {
        var $trigger = $((this.in_modal ? '.modal ' : '') + tip.trigger).filter(':visible').first();
        var extra_trigger = tip.extra_trigger ? $(tip.extra_trigger).filter(':visible').length : true;
        var triggered = $trigger.length && extra_trigger;
        if (triggered) {
            if (!tip.widget) {
                this._activate_tip(tip, tour_name, $trigger);
            } else {
                tip.widget.update($trigger);
            }
        } else {
            this._deactivate_tip(tip);
        }
    },
    _activate_tip: function(tip, tour_name, $anchor) {
        var tour = this.tours[tour_name];
        tip.widget = new Tip(this, $anchor, {
            content: tip.content + (tour.skip_link || ''),
            event_handlers: tour.skip_handler ? [{
                event: 'click',
                selector: '.o_skip_tour',
                handler: tour.skip_handler.bind(this, tip),
            }] : [],
            position: tip.position,
        });
        tip.widget.appendTo(document.body);
        tip.widget.on('tip_consumed', this, this._consume_tip.bind(this, tip, tour_name));

        if (this.running_tour === tour_name) {
            clearTimeout(this.auto_tour_timeout);
            if (tip.run) {
                this._consume_tip(tip, tour_name);
                tip.run.apply(tip);
            }
        }
    },
    _deactivate_tip: function(tip) {
        if (tip.widget) {
            tip.widget.destroy();
            delete tip.widget;
        }
    },
    _consume_tip: function(tip, tour_name) {
        this._deactivate_tip(tip);
        var tour = this.tours[tour_name];
        if (tour.current_step < tour.steps.length - 1) {
            tour.current_step = tour.current_step + 1;
            this.active_tooltips[tour_name] = tour.steps[tour.current_step];
            window.localStorage.setItem(getStepKey(tour_name), tour.current_step);
            if (this.running_tour === tour_name) {
                this._set_running_tour_timeout(tour_name, this.active_tooltips[tour_name]);
            }
        } else {
            this._consume_tour(tour_name);
        }
    },
    _consume_tour: function(tour_name) {
        delete this.active_tooltips[tour_name];
        this.tours[tour_name].current_step = 0;
        window.localStorage.removeItem(getStepKey(tour_name));
        if (this.running_tour === tour_name) {
            window.localStorage.removeItem(getRunningKey());
            this.running_tour = undefined;
            clearTimeout(this.auto_tour_timeout);
        } else {
            this.TourModel.call('consume', [tour_name]);
        }
    },
    _set_running_tour_timeout: function(tour_name, step) {
        if (!step.run) return; // don't set a timeout if the current step requires a manual action
        var self = this;
        this.auto_tour_timeout = setTimeout(function() {
            console.error(_.str.sprintf(_t("Tour %s failed at step %s"), tour_name, step.trigger));
            self._consume_tour(tour_name);
        }, 3000);
    },
});

});
