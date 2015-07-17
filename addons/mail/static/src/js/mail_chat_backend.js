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
        "blur .o_mail_chat_search_input": "_toggle_elements",
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
        event.preventDefault();
        this._toggle_elements();
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
var ChatMailThread = Widget.extend(mail_thread.MailThreadMixin, ControlPanelMixin, {
    template: 'mail.chat.ChatMailThread',
    events: {
        // events from MailThreadMixin
        "click .o_mail_redirect": "on_click_redirect",
        "click .o_mail_thread_message_star": "on_message_star",
        // events specific for ChatMailThread
        "click .o_mail_chat_channel_item": "on_click_channel",
        "click .o_mail_chat_partner_item": "on_click_partner",
        "click .o_mail_chat_channel_unpin": "on_click_partner_unpin",
    },
    init: function (parent, action) {
        console.log(action);
        this._super.apply(this, arguments);
        mail_thread.MailThreadMixin.init.call(this);
        // attributes
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
        // options (from action.params)
        this.options = _.defaults(this.action.params, {
            'display_document_link': true,
            'emoji_list': this.conv_manager.emoji_list,
        });
        // channel business
        this.channels = {};
        this.mapping = {}; // mapping partner_id/channel_id for 'direct message' channel
        this.set('current_channel_id', false);
        this.domain_search = [];
        // channel slots
        this.set('channel_channel', []);
        this.set('channel_direct_message', []);
        this.set('channel_private_group', []);
        this.set('partners', []);
        // models
        this.ChannelModel = new Model('mail.channel', this.context);
        // internal communication
        internal_bus.on('mail_message_receive', this, this.message_receive);
        internal_bus.on('mail_session_receive', this, this.channel_receive);
    },
    willStart: function(){
        return this.channel_fetch_slot();
    },
    start: function(){
        var self = this;
        this._super.apply(this, arguments);
        mail_thread.MailThreadMixin.start.call(this);

        // channel business events
        this.on("change:current_channel_id", this, this.channel_change);
        this.on("change:channel_channel", this, function(){
            self.channel_render('channel_channel');
        });
        this.on("change:channel_private_group", this, function(){
            self.channel_render('channel_private_group');
        });
        this.on("change:partners", this, this.partner_render);

        // search widget for channel
        this.channel_search_widget.insertAfter(this.$('.o_mail_chat_channel_slot_channel_channel'));
        this.channel_search_widget.on('item_create', this, function(name){
            self.channel_create(name, 'public');
        });
        this.channel_search_widget.on('item_clicked', this, function(item){
            self.channel_join_and_get_info(item.id).then(function(channel){
                self.channel_apply(channel);
            });
        });
        // search widget for direct message
        this.partner_search_widget.insertAfter(this.$('.o_mail_chat_channel_slot_partners'));
        this.partner_search_widget.on('item_clicked', this, function(item){
            self.channel_get([item.id]);
            self.partner_add(item);
        });
        // search widget for private group
        this.group_search_widget.insertAfter(this.$('.o_mail_chat_channel_slot_channel_private_group'));
        this.group_search_widget.on('item_create', this, function(name){
            self.channel_create(name, 'private');
        });

        return $.when(this._super.apply(this, arguments)).then(function(res){
            var channel_id = self.context.active_id || self.action.params['default_active_id'] || 'channel_inbox';
            console.log('----> ',channel_id);
            // apply default channel
            if(!_.isString(channel_id)){
                if(_.contains(_.keys(self.channels), channel_id)){
                    self.set('current_channel_id', channel_id);
                }else{
                    self.channel_info(channel_id).then(function(channel){
                        self.channel_apply(channel);
                    });
                }
            }else{
                self.set('current_channel_id', channel_id);
            }
            // update control panel
            var status = {
                breadcrumbs: self.action_manager.get_breadcrumbs(),
            };
            console.log("Breadcriumbs", status);
            self.update_control_panel(status);
            // IM View is activated
            internal_bus.trigger('mail_im_view_active', true);
        });
    },
    destroy: function(){
        internal_bus.trigger('mail_im_view_active', false); // IM View is desactivated
        this._super.apply(this, arguments);
    },
    // events
    on_click_channel: function(event){
        event.preventDefault();
        var channel_id = this.$(event.currentTarget).data('channel-id');
        this.set('current_channel_id', channel_id);
    },
    on_click_partner: function(event){
        if(!this.$(event.target).hasClass('o_mail_chat_channel_unpin')){
            event.preventDefault();
            var partner_id = this.$(event.currentTarget).data('partner-id');
            if(this.mapping[partner_id]){ // don't fetch if channel already in local
                this.set('current_channel_id', this.mapping[partner_id]);
            }else{
                this.channel_get([partner_id]);
            }
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
            // TODO JEM : if unpin current channel, switch to inbox
        });
    },
    // control panel
    cp_update: function(){
        var status = {
            breadcrumbs: self.action_manager.get_breadcrumbs().concat([{'title': current_channel_name, 'action': _.clone(this)}]),
        };
        self.update_control_panel(status);
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
    /**
     * Apply a channel means adding it, and swith to it
     * @param channel : channel header
     */
    channel_apply: function(channel){
        this.channel_add(channel);
        this.set('current_channel_id', channel.id);
    },
    /**
     * Add the given channel, or update it if already exists and loaded
     * @param channel : object with channel values (channel header)
     */
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
    /**
     * Get the channel the current user has with the given partner, and get the channel header
     * @param partner_ids : list of res.partner identifier
     */
    channel_get: function(partner_ids){
        var self = this;
        return this.ChannelModel.call('channel_get', [partner_ids]).then(function(channel){
            self.channel_apply(channel);
        });
    },
    /**
     * Create a channel with the given name and type, and apply it
     * @param channel_name : the name of the channel
     * @param privacy : the privacy of the channel (groups, public, ...)
     */
    channel_create: function(channel_name, privacy){
        var self = this;
        return this.ChannelModel.call('channel_create', [channel_name, privacy]).then(function(channel){
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
        return this.ChannelModel.call('channel_join_and_get_info', [[channel_id]]);
    },
    channel_invite: function(partner_ids){
        return this.ChannelModel.call('channel_invite', [], {"ids" : [this.get('current_channel_id')], 'partner_ids': partner_ids});
    },
    channel_change: function(){
        var self = this;
        var current_channel_id = this.get('current_channel_id');
        var current_channel = this.channels[current_channel_id];
        var current_channel_name = current_channel && current_channel.channel_name || _t('Unknown');

        // virtual channel id (for inbox, or starred channel)
        if(_.isString(current_channel_id)){
            if(current_channel_id == 'channel_inbox'){
                current_channel_name = _t('Inbox');
            }
            if(current_channel_id == 'channel_starred'){
                current_channel_name = _t('Starred');
            }
        }
        // unbold the current channel TODO JEM do rpc to set last dateseen, then unblod !
        this.$('.o_mail_chat_channel_item[data-channel-id="'+current_channel_id+'"]').removeClass('o_mail_chat_channel_unread');
        // TODO JEM this.cp_update([{'title': current_channel_name, 'action': this}], button_flags);

        // mail chat compose message
        this.mail_chat_compose_message = new mail_thread.MailComposeMessage(this, new data.DataSetSearch(this, 'mail.channel', this.context), {
            'emoji_list': this.options.emoji_list,
            'context': _.extend(this.context, {
                'default_res_id': current_channel_id,
            }),
        });
        if(_.isString(current_channel_id)){
            this.$('.o_mail_chat_composer').hide();
        }else{
            this.$('.o_mail_chat_composer').show();
        }
        this.mail_chat_compose_message.replace(this.$('.o_mail_compose_message'));
        this.mail_chat_compose_message.focus();

        // push state
        web_client.action_manager.do_push_state({
            action: this.action.id,
            active_id: current_channel_id,
        });
        this.context['active_id'] = current_channel_id;

        // update control panel
        this.cp_update();

        // fetch the messages
        return this.message_fetch().then(function(messages){
            self.set('messages', self._message_preprocess(messages));
        });
    },
    channel_render: function(channel_slot){
        this.$('.o_mail_chat_channel_slot_' + channel_slot).replaceWith(QWeb.render("mail.chat.ChatMailThread.channels", {'widget': this, 'channel_slot': channel_slot}));
    },
    // partners
    partner_add: function(partner){
        console.log("partner_add", partner);
        var partners = _.filter(this.get('partners'), function(p){ return p.id != partner.id; });
        this.set('partners', partners.concat([partner]));
    },
    partner_render: function(){
        this.$('.o_mail_chat_channel_slot_partners').replaceWith(QWeb.render("mail.chat.ChatThreadMessage.partners", {'widget': this}));
    },
    // from bus
    channel_receive: function(channel){
        // TODO JEM : add it to the channel list and append it to the design
        console.log("CHANNEL RECEIVIE ", channel);
        this.channel_add(channel);
    },
    message_receive: function(message){
        var self = this;
        console.log('MESSAGE RECEIVIE', message, this.get('current_channel_id'));
        // if current channel should reveice message, give it to it
        if(_.contains(message['channel_ids'], this.get('current_channel_id'))){
            this.message_insert([message]);
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
               self.$('.o_mail_chat_sidebar .o_mail_chat_channel_item[data-channel-id="'+channel_id+'"]').addClass('o_mail_chat_channel_unread');
            });
        });
        console.log("MESS check is is_needaction is in mesage", message);
        //TODO JEM: if needaction, add it to inbox + increment badge
        /*
        if(message.needaction){
            this.needaction_increment(message.channel_ids || []);
        }
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
    // override from thread mixin
    message_render: function(){
        this.$('.o_mail_chat_messages_content').html(QWeb.render('mail.chat.ChatMailThread.content', {'widget': this}));
    },
    _message_preprocess: function(messages){ // TODO JEM : remove
        var messages = mail_thread.MailThreadMixin._message_preprocess.apply(this, arguments);
        return messages;
    },
    get_message_domain: function(){
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
    },
});

core.action_registry.add('mail.chat.instant_messaging', ChatMailThread);


return {
    ChatMailThread: ChatMailThread,
};

});
