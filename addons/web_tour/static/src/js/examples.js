odoo.define('web_tour.examples', function (require) {
"use strict";

var core = require('web.core');
var tour = require('web_tour.tour');

var _t = core._t;

tour.register('website_tour_banner_converted_ish', {
    url: "/shop",
}, [{
    trigger: '.o_main_navbar a[data-action=edit]',
    content: _t("This tutorial will guide you to build your home page. We will start by adding a banner."),
    position: 'bottom',
}, {
    trigger: '#snippet_structure .oe_snippet:eq(1)',
    content: _t("Drag the Banner block and drop it in your page."),
    position: 'bottom',
}, {
    trigger: '#wrapwrap .carousel:first div.carousel-content h3',
    extra_trigger: '.oe_overlay_options .oe_options:visible',
    content:   _t("Click in the text and start editing it."),
    position: 'top',
}, {
    // waitNot:   '#wrap .carousel:first div.carousel-content:has(h2:'+
    //     'containsExact('+_t('Your Banner Title')+')):has(h3:'+
    //     'containsExact('+_t('Click to customize this text')+'))',
    trigger:   '.oe_snippet_parent',
    content:   _t("Select the parent container to get the global options of the banner."),
    position: 'bottom',
}, {
    trigger:   '.oe_overlay_options .oe_options:visible',
    content:   _t("Customize any block through this menu. Try to change the background of the banner."),
    position: 'bottom',
}, {
    // waitNot:   '.popover.tour',
    trigger:   '#snippet_structure .oe_snippet:eq(6)',
    content:   _t("Drag the <em>'Features'</em> block and drop it below the banner."),
    position: 'bottom',
}, {
    trigger:   'button[data-action=save]',
    extra_trigger:   '.oe_overlay_options .oe_options:visible',
    content:   _t("Publish your page by clicking on the <em>'Save'</em> button."),
    position: 'bottom',
// }, {
    // waitNot:   'body.editor_enable',
    // content:   _t("Well done, you created your homepage."),
}, {
    // waitNot:   '.popover.tour',
    trigger:   'a[data-action=show-mobile-preview]',
    content:   _t("Let's check how your homepage looks like on mobile devices."),
    position: 'bottom',
}, {
    trigger:   '.modal-dialog:has(#mobile-viewport) button[data-dismiss=modal]',
    content:   _t("Scroll to check rendering and then close the mobile preview."),
    position: 'right',
}, {
    // waitNot:   '.modal-dialog:has(#mobile-viewport)',
    trigger:   '#content-menu-button',
    content:   _t("The 'Content' menu allows you to rename and delete pages or add them to the top menu."),
    position: 'right',
}, {
    // waitNot:   '.popover.tour',
    position: 'bottom',
    trigger:   '#oe_main_menu_navbar a[data-action=new_page]',
    content:   _t("Use this button to add pages"),
}]);

tour.register('auto_tour', {
    auto: true,
    url: "/web?debug=assets#home",
}, [{
    trigger: '.o_app[data-menu-xmlid="base.menu_main_pm"], .oe_menu_toggler[data-menu-xmlid="base.menu_main_pm"]',
    content: 'Let\'s have a look at the <b>Project app</b>.',
    position: 'bottom',
    run: function () {
        $(this.trigger).click();
    },
}, {
    trigger: '.o-kanban-button-new',
    extra_trigger: '.o_project_kanban',
    content: '<b>Create a project</b> that your team is working on.',
    position: 'right',
    run: function () {
        $(this.trigger).click();
    },
}, {
    trigger: 'input.o_project_name',
    content: 'Choose a <b>project name</b>. (e.g. Website Launch, Product Development, Office Party)',
    position: 'right',
    run: function () {
        $(this.trigger).val("Office Party");
        $('.modal-footer .btn-primary').click();
    },
}, {
    trigger: '.o_project_kanban .o_kanban_record:first-child',
    extra_trigger: 'body:not(.modal-open)',
    content: 'Click to <b>open your project</b>.',
    position: 'right',
    // run: function () {
    //  // var $kanban_card = $('.o_kanban_record:contains("Office Party")').first().trigger({isTrigger: false});
    //  var $kanban_card = $('.o_project_kanban_boxes a').first().click();
    // },
}, {
    trigger: ".o_kanban_project_tasks .o_column_quick_create",
    content: "Add columns to setup <b>tasks stages</b>.<br/><i>e.g. Specification &gt; Development &gt; Tests</i>",
    position: "right",
    run: function () {
        $(this.trigger).click();
    },
}, {
    trigger: ".o-kanban-button-new",
    extra_trigger: '.o_kanban_project_tasks .o_kanban_group',
    content: "Now that the project is set up, <b>create a few tasks</b>.",
    position: "right",
    run: function () {
        $(this.trigger).click();
    },
// }, {
//     trigger: ".o_kanban_record:nth-child(3)",
//     extra_trigger: '.o_kanban_project_tasks',
//     content: "<b>Drag &amp; drop tasks</b> between columns as you work on them.",
//     position: "right",
}, {
    trigger: ".o_back_button",
    content: "Use the breadcrumd to <b>go back to tasks</b>.",
    position: "bottom",
    run: function () {
        $(this.trigger).click();
    },
}]);

});