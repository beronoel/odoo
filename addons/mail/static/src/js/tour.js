odoo.define('mail.tour_mail', function (require) {
'use strict';

var core = require('web.core');
var Tour = require('web.Tour');

var _t = core._t;

Tour.register({
    id:   'tour_mail',
    name: _t("Explore Odoo Discuss"),
    path: '/web#action=mail.mail_channel_action_client_chat',

    steps: [
        {
            title:     _t("Welcome!"),
            content:   _t("Odoo Discuss is the best tool to communicate efficiently."),
            popover:   { next: _t("Explore now"), end: _t("Skip") },
        },
        {
            title:     _t("This is your Inbox!"),
            content:   _t("You will find here all the messages addressed to you and every updates about the things you follow."),
            element:   '.o_mail_chat_sidebar > div[data-channel-id="channel_inbox"]',
            placement: 'right',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("This is your Starred section!"),
            content:   _t("Keep all your important messages in this section by starring the posts that really matter"),
            element:   '.o_mail_chat_sidebar > div[data-channel-id="channel_starred"]',
            placement: 'right',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("These are your Channels!"),
            content:   _t("Channels are chat rooms with your colleagues around a project, a general topic (such as sport), or a team (such as R&D). Double click on the channel title to see all the existing ones"),
            element:   '.o_mail_chat_sidebar > div.o_mail_sidebar_title:eq(0)',
            placement: 'right',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("Send Direct Messages from here!"),
            content:   _t("Have one-to-one private discussion with your colleagues by sending them messages from here. Once you talk to someone, you'll find him again here."),
            element:   '.o_mail_chat_sidebar > div.o_mail_sidebar_title:eq(1)',
            placement: 'right',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("Use Private Channels!"),
            content:   _t("Channels may be private too. You can organise internal or private chat rooms from here."),
            element:   '.o_mail_chat_sidebar > div.o_mail_sidebar_title:eq(2)',
            placement: 'right',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("Open your inbox in one click!"),
            content:   _t("Click here to open your inbox directly, wherever you are. Accessing your mails has never been so easy"),
            element:   '.navbar .navbar-right .fa.fa-comment',
            placement: 'bottom',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("@ mentions!"),
            content:   _t("Send an message to someone by mentionning him into it. The message will be automatically forwarded to the mentionned person. In the same way, every message in which you're mentionned will come in your inbox."),
            element:   '.navbar .navbar-right .fa.fa-comment',
            placement: 'bottom',
            popover:   { next: _t("Got it"), fixed: true },
        },
        {
            title:     _t("Invite New Users"),
            content:   _t("You should invite some new users to begin collaborating with them. Click on the icon below to open the App Switcher!"),
            element:   '.navbar-brand.o_menu_toggle',
            placement: 'bottom',
            popover:    { fixed: true },
        },
        {
            waitFor:   '.o_application_switcher',
            title:     _t("Invite New Users"),
            content:   _t("Open your Settings dashboard to add new collaborators!"),
            element:   '.o_app.o_action_app:last()',
            placement: 'bottom',
            popover:    { fixed: true },
        },
        {
            waitFor:   '.o_web_settings_dashboard',
            title:     _t("Invite New Users!"),
            content:   _t("Add some mail addresses in the text area, then click on Invite to send them direct invitations."),
            element:   '.o_web_settings_dashboard_invitations',
            placement: 'bottom',
            popover:   { next: _t("Got it"), fixed: true},
        },
        {
            title:     _t("Fantastic!"),
            content:   _t("Now you're ready to go! Have a wonderful day, and welcome to Odoo!"),
            element:   '.o_web_settings_dashboard_invitations',
            placement: 'bottom',
            popover:   { next: _t("Finish"), next: _t("Skip"), fixed: true},
        },
    ]
});

});
