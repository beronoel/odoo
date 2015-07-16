odoo.define('mail.chat_backend', function (require) {
"use strict";

var bus = require('bus.bus');
var core = require('web.core');
var data = require('web.data');
var Model = require('web.Model');
var pyeval = require('web.pyeval');
var SystrayMenu = require('web.SystrayMenu');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');
var ControlPanelMixin = require('web.ControlPanelMixin');
var SearchView = require('web.SearchView');
var WebClient = require('web.WebClient');

var session = require('web.session');
var utils = require('web.utils');
var web_client = require('web.web_client');

var mail_utils = require('mail.utils');
var mail_chat_common = require('mail.chat_common');
var mail_thread = require('mail.thread');

var _t = core._t;
var QWeb = core.qweb;
var internal_bus = core.bus;


/**
 * Widget handeling the channels, in the backend
 *
 * Responsible to listen the bus and apply action with the received message.  Add layer to coordinate the
 * folded conversation and trigger event for the InstantMessagingView client action (using internal
 * comminication bus). It is a component of the WebClient.
 **/
var ConversationManagerBackend = mail_chat_common.ConversationManager.extend({
    _setup: function(init_data){
        var self = this;
        this._super.apply(this, arguments);
        _.each(init_data['notifications'], function(n){
            self.on_notification(n);
        });
    },
    // window title
    window_title_change: function() {
        this._super.apply(this, arguments);
        var title = undefined;
        if (this.get("waiting_messages") !== 0) {
            title = _.str.sprintf(_t("%d Messages"), this.get("waiting_messages"));
        }
        web_client.set_title_part("im_messages", title);
    },
    // sessions and messages
    session_apply: function(active_session, options){
        if(active_session.is_minimized){
            this._super.apply(this, arguments);
        }else{
            internal_bus.trigger('mail_session_receive', active_session); // TODO JEM : trigger anyway?
        }
    },
    message_receive: function(message) {
        var actual_channel_ids = _.map(_.keys(this.sessions), function(item){
            return parseInt(item);
        });
        var message_channel_ids = message.channel_ids;
        if(_.intersection(actual_channel_ids, message_channel_ids).length){
           this._super.apply(this, arguments);
        }
        // TODO JEM : if not on IMview but minimized conv, don't trigger
        // broadcast the message to the NotificationButton and the InstantMessagingView
        internal_bus.trigger('mail_message_receive', message);
    },
    _message_receive: function(message){
        /*
        var self = this;
        var active_channel_ids = _.map(_.keys(this.sessions), parseInt); // integer as key of a dict is cast as string in javascript
        var channel_to_fetch = _.difference(message.channel_ids, active_channel_ids);
        if (channel_to_fetch.length > 0){
            // fetch channel infos to create conversations
            var _super = this._super.bind(this);
            var def_session = new Model("mail.channel").call("channel_info", [], {"ids" : channel_to_fetch}).then(function(channel_infos){
                _.each(channel_infos, function(channel_info){
                    self.session_apply(channel_info, {'force_open': true});
                });
                _super(message);
            });
        }else{
            // directly apply the message
            this._super(message);
        }
        */
        this._super.apply(this, arguments);
    },
});


/**
 * Widget Minimized Conversation
 *
 * Add layer of WebClient integration, and user fold state handling (comminication with server)
 **/
mail_chat_common.Conversation.include({
    session_update_state: function(state){
        var self = this;
        var args = arguments;
        var super_call = this._super;
        // broadcast the state changing
        return new Model("mail.channel").call("channel_fold", [], {"uuid" : this.get("session").uuid, "state" : state}).then(function(){
            super_call.apply(self, args);
        });
    },
});

/**
 * Widget : Patch for WebClient
 *
 * Create the conversation manager, and attach it to the web_client.
 **/
WebClient.include({
    show_application: function(){
        var self = this;
        var args = arguments;
        var super_call = this._super;
        this.mail_conversation_manager = new ConversationManagerBackend(this);
        this.mail_conversation_manager.start().then(function(){
            super_call.apply(self, args);
            self.mail_conversation_manager.bus.start_polling();
        });
    },
});


/**
 * Widget Top Menu Notification Counter
 *
 * Counter of notification in the Systray Menu. Need to know if InstantMessagingView is displayed to
 * increment (or not) the counter. On click, should redirect to the client action.
 **/
var NotificationTopButton = Widget.extend({
    template:'mail.chat.NotificationTopButton',
    events: {
        "click": "on_click",
    },
    init: function(parent){
        this._super.apply(this, arguments);
        this.set('notifications', []);
        this.im_view_active = false;
    },
    start: function() {
        var self = this;
        this.on("change:notifications", this, this.on_change_notification);
        // handeling InstantMessagingView status (to know when increment notification counter)
        internal_bus.on('mail_message_receive', this, this.add_notification);
        internal_bus.on('mail_im_view_active', this, function(is_active) {
            self.im_view_active = is_active;
        });
        return this._super();
    },
    add_notification: function(message){
        if(!this.im_view_active){
            console.log("ADD NOTIF for ", message);
            this.set('notifications', this.get('notifications').concat([message]));
            // TODO JEM : do ding ding ?
        }
    },
    on_change_notification: function() {
        this.$('.fa-comment').html(this.get('notifications').length || '');
    },
    on_click: function(e){
        e.preventDefault();
        // empty the notifications and redirect to InstantMessagingView
        this.set('notifications', []);
        this.do_action({
            type: 'ir.actions.client',
            tag: 'mail.chat.instant_messaging',
            params: {
                'default_active_id': 'channel_inbox',
            },
        });
    },
});

SystrayMenu.Items.push(NotificationTopButton);


/**
 * Abstract Class to 'Add More/Search' Widget
 *
 * Inputbox using jQueryUI autocomplete to fetch selection, like a Many2One field (on form view)
 * Used to create or pin a mail.channel or a res.partner on the InstantMessagingView
 **/
var AbstractAddMoreSearch = Widget.extend({
    template: 'mail.chat.AbstractAddMoreSearch',
    events: {
        "click .o_mail_chat_add_more_text": "on_click_text",
        "focusout .o_mail_chat_search_input": "_toggle_elements",
    },
    init: function(parent, domain, options){
        this._super.apply(this, arguments);
        var default_options = {
            'can_create': false,
            'label': _t('+ Add More'),
        };
        options = _.defaults(options || {}, default_options);
        this.extra_domain = domain || [];
        this.limit = 10;
        this.can_create = options.can_create;
        this.label = options.label;
    },
    start: function(){
        var self = this;
        this.last_search_val = false;
        this.$input = this.$('.o_mail_chat_search_input');
        this._bind_events();
        return this._super();
    },
    _bind_events: function(){
        // autocomplete
        var self = this;
        this.$input.autocomplete({
            source: function(request, response) {
                self.last_search_val = request.term;
                self.do_search(request.term).done(function(result){
                    if(self.can_create){
                        result.push({
                            'label':  _.str.sprintf('<strong>'+_t("Create %s")+'</strong>', '<em>"'+self.last_search_val+'"</em>'),
                            'value': '_create',
                        });
                    }
                    response(result);
                });
            },
            select: function(event, ui) {
                self.on_click_item(ui.item);
            },
            focus: function(event, ui) {
                event.preventDefault();
            },
            html: true,
        });
    },
    // ui
    _toggle_elements: function(){
        this.$('.o_mail_chat_add_more_text').toggle();
        this.$('.o_mail_chat_add_more_search_bar').toggle();
    },
    on_click_text: function(event){
        this._toggle_elements();
        this.$('.o_mail_chat_search_input').focus();
    },
    // to be redefined
    do_search: function(search_val){
        return $.when();
    },
    on_click_item: function(item){
        if(item.value === '_create'){
            if(this.last_search_val){
                this.trigger('item_create', this.last_search_val);
            }
        }else{
            this.trigger('item_clicked', item);
        }
    },
});

var PartnerAddMoreSeach = AbstractAddMoreSearch.extend({
    do_search: function(search_val){
        var self = this;
        var Partner = new Model("res.partner");
        return Partner.call('im_search', [search_val, this.limit]).then(function(result){
            var values = [];
            _.each(result, function(user){
                values.push(_.extend(user, {
                    'value': user.name,
                    'label': user.name,
                }));
            });
            return values;
        });
    },
});

var ChannelAddMoreSearch = AbstractAddMoreSearch.extend({
    do_search: function(search_val){
        var self = this;
        var Channel = new Model("mail.channel");
        return Channel.call('search_to_join', [search_val, this.extra_domain]).then(function(result){
            var values = [];
            _.each(result, function(channel){
                values.push(_.extend(channel, {
                    'value': channel.channel_name,
                    'label': channel.channel_name,
                }));
            });
            return values;
        });
    },
});

var PrivateGroupAddMoreSearch = AbstractAddMoreSearch.extend({
    _bind_events: function(){
       // don't call the super to avoid autocomplete
       this.$input.on('keyup', this, this.on_keydown);
    },
    on_keydown: function(event){
        if(event.which === $.ui.keyCode.ENTER && this.$input.val()){
            this.trigger('item_create', this.$input.val());
        }
    },
});


/**
 * Widget : Invite People to Channel Dialog
 *
 * Popup containing a 'many2many_tags' custom input to select multiple partners.
 * Search user according to the input, and trigger event when selection is validated.
 **/
var PartnerInviteDialog = Dialog.extend({
    dialog_title: _t('Invite people'),
    template: "mail.chat.PartnerInviteDialog",
    init: function(parent, options){
        this._super.apply(this, arguments);
        this.set("partners", []);
        this.PartnersModel = new Model('res.partner');
        this.limit = 20;
    },
    start: function(){
        var self = this;
        this.$buttons.html($('<button type="button" class="btn btn-primary">'+_t("Add")+'</button>'));
        this.$buttons.on('click', this, this.on_click_add);
        this.$('.o_mail_chat_partner_invite_input').select2({
            width: '100%',
            allowClear: true,
            multiple: true,
            formatResult: function(item){
                if(item.im_status === 'online'){
                    return '<span class="fa fa-circle"> ' + item.text + '</span>';
                }
                return '<span class="fa fa-circle-o"> ' + item.text + '</span>';
            },
            query: function (query) {
                self.PartnersModel.call('im_search', [query.term, self.limit]).then(function(result){
                    var data = [];
                    _.each(result, function(partner){
                        partner['text'] = partner.name;
                        data.push(partner);
                    });
                    query.callback({results: data});
                });
            }
        });
        return this._super.apply(this, arguments);
    },
    on_click_add: function(){
        var data = this.$('.o_mail_chat_partner_invite_input').select2('data');
        if(data.length >= 1){
            var names = _.pluck(data, 'text').join(', ');
            this.do_notify(_t('New people'), _.str.sprintf(_t('You added %s to the conversation.'), names));
            this.trigger('mail_partner_invited', _.pluck(data, 'id'));
        }
        this.close();
    },
});

/**
 * Client Action : Instant Messaging View, inspired by Slack.com
 *
 * Action replacing the Inbox, and the list of group (mailing list, multiple conversation, rooms, ...)
 * Includes real time messages (received and sent), creating group, channel, chat conversation, ...
 **/
var ChatMailTread = Widget.extend(mail_thread.MailThreadMixin, ControlPanelMixin, {
    template: 'mail.chat.ChatMailThread',
    events: {

    },
    init: function (parent, action) {
        this._super.apply(this, arguments);
        mail_thread.MailThreadMixin.init.call(this);
    },
    start: function(){
        this._super.apply(this, arguments);
        mail_thread.MailThreadMixin.start.call(this);
    },
});

var InstantMessagingView = Widget.extend(ControlPanelMixin, {
    template: "mail.chat.im.InstantMessagingView",
    events: {
        "click .o_mail_redirect": "on_click_redirect",
        "click .o_mail_chat_im_sidebar .o_mail_chat_im_channel_item": "on_click_channel",
        "click .o_mail_chat_im_partner_item": "on_click_partner",
        "click .o_mail_chat_im_content .o_mail_chat_im_star": "on_message_star",
        "click .o_mail_chat_im_channel_unpin": "on_click_partner_unpin",
       // "keydown .o_mail_chat_im_compose_message #send_message": "on_keydown",
    },
    init: function (parent, action) {
        console.log('INIT', action);
        this._super.apply(this, arguments);
        this.action_manager = parent;
        this.help_message = action.help || '';
        this.context = action.context;
        this.action = action;
        // components : conversation manager and search widget (channel_type + '_search_widget')
        this.conv_manager = web_client.mail_conversation_manager;
        this.channel_search_widget = new ChannelAddMoreSearch(this, [['channel_type', '=', 'channel']], {'label': _t('+ Subscribe'), 'can_create': true});
        this.group_search_widget = new PrivateGroupAddMoreSearch(this, [], {'label': _t('+ New private group'), 'can_create': true});
        this.partner_search_widget = new PartnerAddMoreSeach(this);
        // emoji
        this.emoji_list = this.conv_manager.emoji_list;
        this.emoji_substitution = this.conv_manager.emoji_substitution;
        // channel business
        this.channels = {};
        this.mapping = {}; // mapping partner_id/channel_id for 'direct message' channel
        this.set('current_channel_id', false);
        this.set('current_messages', []);
        this.domain_search = [];
        // channel slots
        this.set('channel_channel', []);
        this.set('channel_direct_message', []);
        this.set('channel_private_group', []);
        this.set('partners', []);
        // models
        this.ChannelModel = new Model('mail.channel', this.context);
        this.MessageDatasetSearch = new data.DataSetSearch(this, 'mail.message');
        // internal communication
        internal_bus.on('mail_message_receive', this, this.message_receive);
        internal_bus.on('mail_session_receive', this, this.channel_receive);
    },
    willStart: function(){
        console.log("WILL START slack");
        return this.channel_fetch_slot();
    },
    start: function(){
        console.log("START slack");
        var self = this;
        // control panel elements
        this.control_elements = {};
        this.buttons = {};
        // channel business events
        this.on("change:current_messages", this, this.message_render);
        this.on("change:current_channel_id", this, this.channel_change);
        this.on("change:channel_channel", this, function(){
            self.channel_render('channel_channel');
        });
        this.on("change:channel_private_group", this, function(){
            self.channel_render('channel_private_group');
        });
        this.on("change:partners", this, this.partner_render);
        // search widget for channel
        this.channel_search_widget.insertAfter(this.$('.o_mail_chat_im_sidebar_slot_channel_channel'));
        this.channel_search_widget.on('item_create', this, function(name){
            self.channel_create(name, 'public').then(function(channel){
                self.channel_apply(channel);
            });
        });
        this.channel_search_widget.on('item_clicked', this, function(item){
            self.channel_join_and_get_info(item.id).then(function(channel){
                self.channel_apply(channel);
            });
        });
        // search widget for direct message
        this.partner_search_widget.insertAfter(this.$('.o_mail_chat_im_sidebar_slot_partners'));
        this.partner_search_widget.on('item_clicked', this, function(item){
            self.channel_get([item.id]);
            self.partner_add(item);
        });
        // search widget for private group
        this.group_search_widget.insertAfter(this.$('.o_mail_chat_im_sidebar_slot_channel_private_group'));
        this.group_search_widget.on('item_create', this, function(name){
            self.channel_create(name, 'private').then(function(channel){
                self.channel_apply(channel);
            });
        });
        // mail chat compose message
        this.mail_chat_compose_message = new mail_thread.MailComposeMessage(this, new data.DataSetSearch(this, 'mail.channel', this.context), {'emoji_list':this.emoji_list});
        this.mail_chat_compose_message.start();
            //console.log(this.mail_chat_compose_message);
            //console.log(mail_thread.MailComposeMessage);

        this.mail_chat_compose_message.on('mail_send_message', this, function(v){
            self.message_send(v.message, v.attachment_ids);
        });
        return $.when(this._super.apply(this, arguments), self.cp_render_searchview()).then(function(res){
            self.cp_render_buttons();
            self.cp_update();
            // apply default channel
            if(self.context.active_id){
                if(_.contains(_.keys(self.channels), self.context.active_id)){
                    self.set('current_channel_id', self.context.active_id);
                }else{
                    self.channel_info(self.context.active_id).then(function(channel){
                        self.channel_apply(channel);
                    });
                }
            }else{
                self.set('current_channel_id', self.action.params['default_active_id'] || 'channel_inbox');
            }
            // IM View is activated
            internal_bus.trigger('mail_im_view_active', true);
        });
    },
    destroy: function(){
        internal_bus.trigger('mail_im_view_active', false); // IM View is desactivated
        this._super.apply(this, arguments);
    },
    // control panel
    cp_update: function(breadcrumbs, button_flags){
        // use ControlPanel Mixin for search bar
        var self = this;
        breadcrumbs =  breadcrumbs || self.action_manager.get_breadcrumbs();
        self.update_control_panel({
            breadcrumbs: breadcrumbs,
            cp_content: {
                $buttons: self.control_elements.$buttons,
                $searchview: self.control_elements.$searchview,
                $searchview_buttons: self.control_elements.$searchview_buttons,
                $pager: self.control_elements.$pager,
            },
            searchview: self.searchview,
        });
        // clean search view filter
        this.searchview.set_default_filters().then(function(){
            self.domain_search = [];
        });
        // hide buttons according to given flags
        _.each(_.keys(button_flags), function(k){
            var $elem = self.buttons[k];
            if(!button_flags[k]){
                $elem.hide();
            }else{
                $elem.show();
            }
        });
    },
    cp_render_buttons: function() {
        this.control_elements.$buttons = $(QWeb.render("mail.chat.im.ControlButtons", {'widget': this}));
        this.buttons.$minimize = this.control_elements.$buttons.filter('.o_mail_chat_im_button_minimize').on('click', this, this.on_click_minimize);
        this.buttons.$invite = this.control_elements.$buttons.filter('.o_mail_chat_im_button_invite').on('click', this, this.on_click_invite);
        this.control_elements.$pager = $(QWeb.render("mail.chat.im.MoreButton", {'widget': this}));
        this.control_elements.$pager.find('.o_mail_chat_im_button_unsubscribe').on('click', this, this.on_click_unsubscribe);
        this.control_elements.$pager.find('.o_mail_chat_im_button_settings').on('click', this, this.on_click_settings);
        this.buttons.$more = this.control_elements.$pager;
    },
    cp_render_searchview: function(){
        var self = this;
        var options = {
            $buttons: $("<div>"),
            action: this.action,
        };
        var view_id = (this.action && this.action.search_view_id && this.action.search_view_id[0]) || false;
        this.searchview = new SearchView(this, this.MessageDatasetSearch, view_id, {}, options);

        this.searchview.on('search_data', this, this.on_search);
        return $.when(this.searchview.appendTo($("<div>"))).done(function() {
            self.control_elements.$searchview = self.searchview.$el;
            self.control_elements.$searchview_buttons = self.searchview.$buttons.contents();
            self.searchview.$buttons.find('.oe-groupby-menu').hide(); // hide the 'group by' button
        });
    },
    on_search: function(domains, contexts, groupbys){
        var self = this;
        return pyeval.eval_domains_and_contexts({
            domains: [this.action.domain || []].concat(domains || []),
            contexts: [this.context].concat(contexts || []),
            group_by_seq: groupbys || [],
        }).done(function (results) {
            if (results.error) {
                throw new Error(_.str.sprintf(_t("Failed to evaluate search criterions")+": \n%s", JSON.stringify(results.error)));
            }
            self.domain_search = results['domain'];
            self.message_fetch(self.get_current_domain(), {'reset': true});
        });
    },
    // event actions
    on_click_minimize: function(event){
        event.preventDefault();
        var channel_uuid = this.channels[this.get('current_channel_id')].uuid;
        return this.ChannelModel.call("channel_minimize", [channel_uuid, true]);
    },
    on_click_channel: function(event){
        event.preventDefault();
        var channel_id = this.$(event.currentTarget).data('channel-id');
        this.set('current_channel_id', channel_id);
    },
    on_click_partner: function(event){
        if(!this.$(event.target).hasClass('o_mail_chat_im_channel_unpin')){
            event.preventDefault();
            var partner_id = this.$(event.currentTarget).data('partner-id');
            if(this.mapping[partner_id]){ // don't fetch if channel alerady in local
                this.set('current_channel_id', this.mapping[partner_id]);
            }else{
                this.channel_get([partner_id]);
            }
        }
    },
    on_click_needaction: function(event){
        //TODO JEM ???
        if(!this.$(event.target).hasClass('o_mail_chat_needaction')){
            event.preventDefault();
            var channel_id = this.$(event.currentTarget).data('channel-id');
            console.log('JUMP to channel view, with defautl search filter activated OR NOT according to FP', channel_id);
        }
    },
    on_click_partner_unpin: function(event){
        event.preventDefault();
        var self = this;
        var $source = this.$(event.currentTarget);
        var partner_id = $source.data('partner-id');
        var channel_id = this.mapping[partner_id];
        var channel = this.channels[channel_id];
        this.channel_unpin(channel.uuid).then(function(){
            self.set('partners', _.filter(self.get('partners'), function(p){ return p.id !== partner_id; }));
            self.channel_remove(channel_id);
            delete self.mapping[partner_id];
        });
    },
    on_click_invite: function(event){
        event.preventDefault();
        var self = this;
        var dialog = new PartnerInviteDialog(this, {
            size: 'medium',
        });
        dialog.open();
        dialog.on('mail_partner_invited', this, function(partner_ids){
            self.channel_invite(partner_ids);
        });
    },
    on_click_unsubscribe: function(event){
        var self = this;
        return this.ChannelModel.call("action_unfollow", [], {"ids" : [this.get('current_channel_id')]}).then(function(r){
            var m = _.str.sprintf(_t("You are not member of %s"), self.channels[self.get('current_channel_id')].channel_name);
            self.do_notify(_t('Channel Unsubscription'), m);
            self.channel_remove(self.get('current_channel_id'));
            self.set('current_channel_id', 'channel_inbox');
        });
    },
    on_click_settings: function(event){
        event.preventDefault();
        this.do_action({
            type: 'ir.actions.act_window',
            res_model: 'mail.channel',
            res_id: this.get('current_channel_id'),
            view_mode: 'form',
            view_type: 'form',
            views: [[false, 'form']],
        });
    },
    on_message_star: function(event){
        var $source = this.$(event.currentTarget);
        var mid = $source.data('message-id');
        var is_starred = !$source.hasClass('o_mail_starred');

        return new Model('mail.message').call('set_message_starred', [[mid], is_starred]).then(function(res){
            $source.toggleClass('o_mail_starred');
        });
    },
    /**
     * Generic redirect action : redirect to the form view if the
     * click node contains 'data-oe-model' and 'data-oe-id'.
     */
    on_click_redirect: function(event){
        event.preventDefault();
        var res_id = $(event.target).data('oe-id');
        var res_model = $(event.target).data('oe-model');
        web_client.action_manager.do_push_state({
            'model': res_model,
            'id': res_id,
            'title': this.record_name,
        });
        this.do_action({
            type:'ir.actions.act_window',
            view_type: 'form',
            view_mode: 'form',
            res_model: res_model,
            views: [[false, 'form']],
            res_id: res_id,
        });
    },
    // channels
    channel_fetch_slot: function(){
        var self = this;
        return this.ChannelModel.call("channel_fetch_slot").then(function(result){
            self.set('partners', result['partners']);
            self.mapping = result['mapping'];
            self._channel_slot(_.omit(result, 'partners', 'mapping'));
        });
    },
    _channel_slot: function(fetch_result){
        var self = this;
        var channel_slots = _.keys(fetch_result);
        _.each(channel_slots, function(slot){
            // update the channel slot
            self.set(slot, fetch_result[slot]);
            // flatten the result : update the complete channel list
            _.each(fetch_result[slot], function(channel){
                self.channels[channel.id] = channel;
            });
        });
    },
    channel_apply: function(channel){
        this.channel_add(channel);
        this.set('current_channel_id', channel.id);
    },
    channel_add: function(channel){
        var channel_slot = this.get_channel_slot(channel);
        var existing = this.get(channel_slot);
        if(_.contains(_.pluck(existing, 'id'), channel.id)){
            // update the old channel
            var filtered_channels = _.filter(this.get(channel_slot), function(item){ return item.id != channel.id; });
            this.set(channel_slot, filtered_channels.concat([channel]));
        }else{
            // simply add the reveiced channel
            this.set(channel_slot, existing.concat([channel]));
        }
        // also update the flatten list
        this.channels[channel.id] = channel;

        // update the mapping for 'direct message' channel, and the partner list
        if(channel_slot === 'channel_direct_message'){
            var partner = channel.direct_partner[0];
            this.mapping[partner.id] = channel.id;
            this.partner_add(partner);
        }
    },
    channel_remove: function(channel_id){
        var channel = this.channels[channel_id];
        var slot = this.get_channel_slot(channel);
        this.set(slot, _.filter(this.get(slot), function(c){ return c.id !== channel_id; }));
        delete this.channels[channel_id];
    },
    channel_get: function(partner_ids){
        var self = this;
        return this.ChannelModel.call('channel_get', [partner_ids]).then(function(channel){
            self.channel_apply(channel);
        });
    },
    channel_info: function(channel_id){
        var self = this;
        return this.ChannelModel.call('channel_info', [[channel_id]]).then(function(channels){
            return channels[0];
        });
    },
    channel_unpin: function(uuid){
        return this.ChannelModel.call('channel_pin', [uuid, false]);
    },
    channel_join_and_get_info: function(channel_id){
        return this.ChannelModel.call('channel_join_and_get_info', [[channel_id]]).then(function(channel){
            return channel;
        });
    },
    channel_invite: function(partner_ids){
        return this.ChannelModel.call('channel_invite', [], {"ids" : [this.get('current_channel_id')], 'partner_ids': partner_ids});
    },
    channel_create: function(channel_name, channel_type){
        return this.ChannelModel.call('channel_create', [channel_name, channel_type]).then(function(channel){
            return channel;
        });
    },
    channel_change: function(){
        var self = this;
        var current_channel_id = this.get('current_channel_id');
        var current_channel = this.channels[current_channel_id];
        var current_channel_name = current_channel && current_channel.channel_name || _t('Unknown');
        var button_flags = {
            $minimize: true,
            $invite: true,
            $more: true,
        };
        // virtual channel id (for inbox, or starred channel)
        if(_.isString(current_channel_id)){
            if(current_channel_id == 'channel_inbox'){
                current_channel_name = _t('Inbox');
            }
            if(current_channel_id == 'channel_starred'){
                current_channel_name = _t('Starred');
            }
            button_flags.$minimize = false;
            button_flags.$invite = false;
            button_flags.$more = false;
        }else{
            if(current_channel && this.get_channel_slot(current_channel) === 'channel_direct_message'){
                button_flags.$invite = false;
                button_flags.$more = false;
            }
        }
        // highlight and unbold the current channel
        this.$('li[data-channel-id]').removeClass('active');
        this.$('li[data-channel-id="'+current_channel_id+'"]').addClass('active').removeClass('o_mail_chat_im_unread');
        this.cp_update([{'title': current_channel_name, 'action': this}], button_flags);
        // fetch the messages (do it after cp_update which update the domain search)
        return this.message_fetch(this.get_current_domain(), {'reset': true, 'thread_level': 1});
    },
    channel_receive: function(channel){
        // TODO JEM : add it to the channel list and append it to the design
        console.log("CHANNEL RECEIVIE ", channel);
        this.channel_add(channel);
    },
    channel_render: function(channel_slot){
        console.log("CHANNEL RENDER", channel_slot);
        this.$('.o_mail_chat_im_sidebar_slot_' + channel_slot).replaceWith(QWeb.render("mail.chat.im.ChannelList", {'widget': this, 'channel_slot': channel_slot}));
    },
    // messages
    message_fetch: function(domain, options){
        var self = this;
        var default_options = {
            'reset': false, // if reset, current_messages will be replaced. Otherwise the new ones will be append
            'limit': 3,
            'limit_child': 2,
            'thread_level': 0, // 0 is required to flatten the messages
            'context': this.context || {},
            'default_parent_id': undefined,
        };
        options = _.defaults(options, default_options);

        return this.MessageDatasetSearch.call('message_read_wrapper', [
                // ids force to read
                //ids === false ? undefined : ids && ids.slice(0, this.options.fetch_limit),
                false,
                // domain if not give ids
                domain,
                // context
                options.context,
                // thread_level
                options.thread_level,
                // parent_id
                options.default_parent_id,
                // limits
                options.limit,
                options.limit_child
            ]
        ).then(function(result){
            var messages = _.sortBy(result['threads'][0], function(m){ return m.date; });
            messages = self._message_preprocess(messages);
            if(!options.reset){
                messages = this.get('current_messages').concat(messages);
            }
            self.set('current_messages', messages);
        });
    },
    _message_preprocess: function(messages){
        var self = this;
        _.map(messages, function(m){
            if(m.body){
                m.body = mail_utils.apply_shortcode(m.body, self.emoji_substitution);
            }
            _.each(m.attachment_ids, function(a){
                a.url = session.url('/web/binary/saveas', {model: 'ir.attachment', field: 'datas', filename_field: 'name', 'id': a.id});
            });
            //m.create_date = moment(time.str_to_datetime(m.create_date)).format('YYYY-MM-DD HH:mm:ss');
            return m;
        });
        return messages;
    },
    message_render: function(){
        var self = this;
        var messages = this.get('current_messages');
        var current_channel_id = this.get('current_channel_id');

        this.undelegateEvents();
        if(_.isString(current_channel_id)){ // display Personnal Content (Inbox or Starred)
            this.$('.o_mail_chat_im_content').html(QWeb.render("mail.chat.im.PersonalContent", {'widget': this}));
        }else{
            this.$('.o_mail_chat_im_content').html(QWeb.render("mail.chat.im.ConversationContent", {'widget': this}));
            // append the mail chat compose message its generated DOM contains default value
            this.mail_chat_compose_message.clean_attachments();
            this.mail_chat_compose_message.insertAfter(this.$('.o_mail_chat_im_messages'));
            this.$('.o_mail_compose_message_input').focus();
        }
        this.delegateEvents();
    },
    message_receive: function(message){
        var self = this;
        console.log('message_receive', message, this.get('current_channel_id'));
        // if current channel should reveice message, give it to it
        if(_.contains(message['channel_ids'], this.get('current_channel_id'))){
            this.set('current_messages', this.get('current_messages').concat(this._message_preprocess([message])));
        }
        // for other message channel, get the channel if not loaded yet, and bolded them
        var other_message_channel_ids = _.without(message['channel_ids'], this.get('current_channel_id'));
        var active_channel_ids = _.map(_.keys(this.channels), parseInt); // integer as key of a dict is cast as string in javascript
        var channel_to_fetch = _.difference(other_message_channel_ids, active_channel_ids);
        // fetch unloaded channels and add it
        var def = $.Deferred();
        if(channel_to_fetch.length >= 1){
            def = this.ChannelModel.call("channel_info", [], {"ids" : channel_to_fetch}).then(function(channels){
                _.each(channels, function(channel){
                    self.channel_add(channel);
                });
            });
        }else{
            def.resolve();
        }
        // bold the channel to indicate unread messages
        def.then(function(){
            // bold channel having unread messages
            _.each(other_message_channel_ids, function(channel_id){
               self.$('.o_mail_chat_im_sidebar .o_mail_chat_im_channel_item[data-channel-id="'+channel_id+'"]').addClass('o_mail_chat_im_unread');
            });
        });
        //TODO JEM: if needaction, add it to inbox + increment badge
        if(message.needaction){
            this.needaction_increment(message.channel_ids || []);
        }
    },
    message_send: function(message, attachment_ids){
        attachment_ids = attachment_ids || [];
        var current_channel = this.channels[this.get('current_channel_id')];
        return session.rpc("/mail/chat_post", {uuid: current_channel.uuid, message_content: message, attachment_ids: attachment_ids});
    },
    // partners
    partner_add: function(partner){
        console.log("partner_add", partner);
        var partners = _.filter(this.get('partners'), function(p){ return p.id != partner.id; });
        this.set('partners', partners.concat([partner]));
    },
    partner_render: function(){
        this.$('.o_mail_chat_im_sidebar_slot_partners').replaceWith(QWeb.render("mail.chat.im.PartnerList", {'widget': this}));
    },
    // needaction
    needaction_increment: function(channel_ids){
        console.log("needaction_increment", channel_ids);
        var self = this;
        /*
        _.each(channel_ids, function(channel_id){
            var current = self.channels[channel_id];
            var slot = self.get_channel_slot(channel);

            var index = _.findIndex(self.get(slot), function(channel){
                return channel.id === current.id;
            });
            var channels = self.get(slot);
            if(index != -1){ // -1 means not found
                self.channels[channel.id].message_needaction_counter += 1;
                channels[index].message_needaction_counter += 1; // TODO JEM check if working fine
                self.set(slot, channels); // TODO JEM check not trigger render_channel !!!
                self.$('.o_mail_chat_needaction[data-channel-id="'+channel_id+'"]').html(channels[index].message_needaction_counter);
                self.$('.o_mail_chat_needaction[data-channel-id="'+channel_id+'"]').show();
            }
        });
        */
    },
    needaction_decrement: function(channel_id){
        var self = this;
        /*
        return this.ChannelModel.call('channel_seen', [], {"ids" : [channel_id]}).then(function(){
            self.needaction[channel_id] = 0;
            self.$('.o_mail_chat_needaction[data-channel-id="'+channel_id+'"]').html(self.needaction[channel_id]);
            self.$('.o_mail_chat_needaction[data-channel-id="'+channel_id+'"]').hide();
        });
        */
    },
    // utils
    get_channel_slot: function(channel){
        if(channel.channel_type === 'channel'){
            if(channel.public === 'private'){
                return 'channel_private_group';
            }
            return 'channel_channel';
        }
        if(channel.channel_type === 'chat'){
            return 'channel_direct_message';
        }
    },
    get_current_domain: function(){
        // default channel domain
        var current_channel_id = this.get('current_channel_id');
        var domain = [['channel_ids', 'in', current_channel_id]];
        // virtual channel id (for inbox, or starred channel)
        if(_.isString(current_channel_id)){
            if(current_channel_id == 'channel_inbox'){
                domain = [['needaction', '=', true]];
            }
            if(current_channel_id == 'channel_starred'){
                domain = [['starred', '=', true]];
            }
        }
        // add search domain
        domain = domain.concat(this.domain_search);
        return domain;
    }
});

core.action_registry.add('mail.chat.instant_messaging', ChatMailTread);


return {
    InstantMessagingView: InstantMessagingView,
};

});
