odoo.define('web.tour_test', function(require) {
"use strict";

// TO REMOVE THIS BEFORE MERGING IN MASTER

var tour = require('web_tour.tour');

// tour.register('some tooltip', {
//     trigger: '.o_app[data-action-id="147"]',
//     title: 'Hello Project',
//     content: 'so much better than Trello',
//     position: 'bottom',
// });

// tour.register('kanban first record', {
//     trigger: '.o_kanban_view .o_kanban_record:first-child',
//     title: 'First kanban record',
//     content: 'You rock',
//     position: 'right',
// });


tour.register('project_example', [{
    trigger: '.o_app[data-action-id="147"]',
    content: 'so much better than Trello',
    position: 'right',
}, {
    trigger: '.o-kanban-button-new',
    extra_trigger: '.o_project_kanban',
    content: 'Click here to create a new project',
    position: 'right',
}, {
    trigger: '.o_project_form h1',
    content: 'FUCKFUCKFUCK',
    position: 'right',
}, {
    trigger: '.o_menu_sections li:first-child a',
    extra_trigger: '.o_project_form.o_form_readonly',
    content: 'Project can be accessed from the dashboard',
    position: 'right',
}, {
    trigger: '.o_project_kanban .o_kanban_record:first-child',
    content: 'Click here to open your new project',
    position: 'right',
}, {
    trigger: ".o_kanban_project_tasks .o_column_quick_create",
    content: "Tasks in a project are created in columns, representing their state in the project",
    position: "top right"
}, {
    trigger: ".o_kanban_project_tasks .o_kanban_quick_create",
    content: "Don't worry, you can change it later if you want",
    position: "right"
}]);


// Example: automatic tour

// tour.register('some_other_tour', {
//     url: "/some/url/action=13",
// }, [{
//     trigger: "some css selector 1",
//     content: _t("tooltip 1 content"),
//     position: "bottom"
// }, function () {
//     $('.o_css_selector').click();
// }, {
//     trigger: "some css selector 2",
//     content: _t("tooltip 2 content"),
//     position: "left"
// }, function () {
//     $('.o_css_selector').click();
// }, {
//     trigger: "some css selector 3",
//     content: _t("tooltip 3 content"),
//     position: "right"
// }, function () {
//     $('.o_css_selector input')
//         .val("salut");
//     $('.ocss button').click();
// }, {
//     trigger: "some css selector 3",
//     content: _t("tooltip 3 content"),
//     position: "right"
// }]);

});
