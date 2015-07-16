odoo.define('mail.chat_common', function (require) {
"use strict";

var bus = require('bus.bus');
var core = require('web.core');
var session = require('web.session');
var time = require('web.time');
var Widget = require('web.Widget');
var mail_utils = require('mail.utils');

var _t = core._t;
var QWeb = core.qweb;

var NBR_LIMIT_HISTORY = 20;


// TODO JEM :
//      clean options (in init)
//      clean options of session_apply (force_open may be not used)


/**
 * Widget handeling the sessions/conversations
 *
 * Responsible to listen the bus and do the correct action according to the received notifications (fetch
 * conversation, add message, ...)
 **/
var ConversationManager = Widget.extend({
    init: function(parent, options) {
        var self = this;
        this._super(parent);
        this.options = _.clone(options) || {};
        _.defaults(this.options, {
            inputPlaceholder: _t("Say something..."),
            defaultMessage: null,
            defaultUsername: _t("Visitor"),
            force_open: false,
            load_history: true,
            focus: false,
        });
        // emoji
        this.emoji_list = [];
        this.emoji_substitution = {};

        // business
        this.sessions = {};
        this.bus = bus.bus;
        this.bus.on("notification", this, this.on_notification);

        // ui
        this.set("right_offset", 0);
        this.set("bottom_offset", 0);
        this.on("change:right_offset", this, this.calc_positions);
        this.on("change:bottom_offset", this, this.calc_positions);

        this.set("waiting_messages", 0);
        this.on("change:waiting_messages", this, this.window_title_change);
        $(window).on("focus", _.bind(this.window_focus, this));
        this.window_title_change();
    },
    start: function(){
        var self = this;
        return $.when(session.rpc("/mail/chat_init"), this._super.apply(this, arguments)).then(function(result){
            self._setup(result);
        });
    },
    _setup: function(init_data){
        console.log("emoji loeded");
        var self = this;
        this.emoji_list = init_data['emoji'];
        this.emoji_substitution = {}
        _.each(init_data['emoji'], function(emoji){
            self.emoji_substitution[emoji['source']] = emoji['substitution'];
        });
        this.options['emoji'] = this.emoji_substitution;
    },
    on_notification: function(notification, options) {
        var self = this;
        var channel = notification[0];
        var message = notification[1];
        var regex_uuid = new RegExp(/(\w{8}(-\w{4}){3}-\w{12}?)/g);
        // (dbname, 'res.partner', partner_id) receive only the new mail.channel header
        if((Array.isArray(channel) && (channel[1] === 'res.partner')) || (regex_uuid.test(channel))){
            // activate the received session
            if(message.uuid){
                this.session_apply(message, options);
            }
        }
        // (dbname, 'mail.channel', channel_id) receive only the mail.message of the channel
        if((Array.isArray(channel) && (channel[1] === 'mail.channel')) || (regex_uuid.test(channel))){
            // message to display in the chatview
            if (message.message_type) {
                self.message_receive(message);
            }
        }
    },
    // window focus unfocus beep and title
    window_focus: function() {
        this.set("waiting_messages", 0);
    },
    window_beep: function() {
        if (typeof(Audio) === "undefined") {
            return;
        }
        var audio = new Audio();
        var ext = audio.canPlayType("audio/ogg; codecs=vorbis") ? ".ogg" : ".mp3";
        audio.src = session.url("/mail/static/src/audio/ting") + ext;
        audio.play();
    },
    window_title_change: function() {
        var title = undefined;
        if (this.get("waiting_messages") !== 0) {
            this.window_beep();
        }
    },
    // sessions and messages
    session_apply: function(active_session, options){
        // options used by this function : force_open and focus (load_history can be usefull)
        var self = this;
        options = _.extend(_.clone(this.options), options || {});

        // force open
        var session = _.clone(active_session);
        if(options['force_open']){
            session.state = 'open';
        }
        // create/get the conversation widget
        var conv = this.sessions[session.id];
        if (! conv) {
            if(session.state !== 'closed'){
                conv = new Conversation(this, this, session, options);
                conv.appendTo($("body"));
                conv.on("destroyed", this, _.bind(this.session_delete, this));
                this.sessions[session.id] = conv;
                this.calc_positions();
            }
        }else{
            conv.set("session", session);
        }
        // if force open, broadcast it
        if(options['force_open'] && active_session.state !== 'open'){
            conv.session_update_state('open');
        }
        // apply the focus
        if (options['focus']){
            conv.focus();
        }
        return conv;
    },
    session_delete: function(channel_id){
        delete this.sessions[channel_id];
        this.calc_positions();
    },
    message_receive: function(message) {
        /* TODO JEM : check if we keep this
        var self = this;
        var session_id = message.to_id[0];
        var uuid = message.to_id[1];
        var from_id = message['from_id'] ? message['from_id'][0] : false;
        if (! this.get("window_focus") && from_id != this.get_current_uid()) {
            this.set("waiting_messages", this.get("waiting_messages") + 1);
        }
        */
        this._message_receive(message);
    },
    /**
     * private implementation of adding a message in all its channels
     * /!\ Suppose the channel are already loaded in the ConversationManager /!\
     * @param {object} the nearly received message
     */
    _message_receive: function(message){
        var self = this;
        _.each(message.channel_ids, function(channel_id){
            self.sessions[channel_id].message_receive(message);
        });
    },
    // others
    get_current_uid: function(){
        return session && !_.isUndefined(session.uid) ? session.uid : false;
    },
    calc_positions: function() {
        var self = this;
        var current = this.get("right_offset");
        _.each(this.sessions, function(s) {
            s.set("bottom_position", self.get("bottom_offset"));
            s.set("right_position", current);
            current += s.$().outerWidth(true);
        });
    },
    destroy: function() {
        $(window).off("unload", this.unload);
        $(window).off("focus", this.window_focus);
        $(window).off("blur", this.window_blur);
        return this._super();
    }
});

// TODO JEM :
//      remove action-options dropdown
//      change style of message rendering
//      clean preprocess messages
var Conversation = Widget.extend({
    className: "openerp_style oe_im_chatview",
    events: {
        "keydown input": "keydown",
        "click .oe_im_chatview_close": "click_close",
        "click .oe_im_chatview_header": "click_header"
    },
    init: function(parent, c_manager, session, options) {
        this._super(parent);
        this.c_manager = c_manager;
        this.options = options || {};
        this.loading_history = true;
        this.set("messages", []);
        this.set("session", session);
        this.set("right_position", 0);
        this.set("bottom_position", 0);
        this.set("pending", 0);
        this.inputPlaceholder = this.options.defaultInputPlaceholder;
    },
    start: function() {
        var self = this;
        // ui
        self.$().append(QWeb.render("im_chat.Conversation", {widget: self}));
        self.on("change:right_position", self, self.calc_pos);
        self.on("change:bottom_position", self, self.calc_pos);
        self.on("change:pending", self, _.bind(function() {
            if (self.get("pending") === 0) {
                self.$(".nbr_messages").text("");
            } else {
                self.$(".nbr_messages").text("(" + self.get("pending") + ")");
            }
        }, self));
        self.full_height = self.$().height();
        self.calc_pos();
        // business
        self.on("change:session", self, self.session_update);
        self.on("change:messages", self, self.render_messages);
        self.$('.oe_im_chatview_content').on('scroll',function(){
            if($(this).scrollTop() === 0){
                self.message_history();
            }
        });
        if(self.options['load_history']){ // load history if asked
            self.message_history();
        }
        // prepare the header and the correct state
        self.session_update();
        return self._super.apply(this, arguments);
    },
    // ui
    show: function(){
        this.$().animate({
            height: this.full_height
        });
        this.set("pending", 0);
    },
    hide: function(){
        this.$().animate({
            height: this.$(".oe_im_chatview_header").outerHeight()
        });
    },
    calc_pos: function() {
        this.$().css("right", this.get("right_position"));
        this.$().css("bottom", this.get("bottom_position"));
    },
    // session
    session_update_state: function(state){
        var session = this.get('session');
        session.state = state;
        this.set('session', session);
    },
    session_update: function(){
        // built the name
        /*
        var names = [];
        _.each(this.get("session").users, function(user){
            if( (session.uid !== user.id) && !(_.isUndefined(session.uid) && !user.id) ){
                names.push(user.name);
            }
        });
        */
        var name = this.get("session").channel_name || '???'; // TODO JEM
        this.$(".header_name").text(name);
        this.$(".header_name").attr('title', name);
        // update the fold state
        if(this.get("session").state){
            if(this.get("session").state === 'closed'){
                this.destroy();
            }else{
                if(this.get("session").state === 'open'){
                    this.show();
                }else{
                    this.hide();
                }
            }
        }
    },
    // messages
    message_history: function(){
        var self = this;
        if(this.loading_history){
            var data = {uuid: self.get("session").uuid, limit: NBR_LIMIT_HISTORY};
            var lastid = _.first(this.get("messages")) ? _.first(this.get("messages")).id : false;
            if(lastid){
                data.last_id = lastid;
            }
            session.rpc("/mail/chat_history", data).then(function(messages){
                if(messages){
                    self.insert_messages(messages);
                    if(messages.length != NBR_LIMIT_HISTORY){
                        self.loading_history = false;
                    }
                }else{
                    self.loading_history = false;
                }
            });
        }
    },
    message_receive: function(message) {
        if (this.get('session').state === 'open') {
            this.set("pending", 0);
        } else {
            this.set("pending", this.get("pending") + 1);
        }
        this.insert_messages([message]);
        this._go_bottom();
    },
    message_send: function(message) {
        var self = this;
        var send_it = function() {
            return session.rpc("/mail/chat_post", {uuid: self.get("session").uuid, message_content: message});
        };
        var tries = 0;
        send_it().fail(function(error, e) {
            e.preventDefault();
            tries += 1;
            if (tries < 3)
                return send_it();
        });
    },
    insert_messages: function(messages){
        var self = this;
        // avoid duplicated messages
        messages = _.filter(messages, function(m){ return !_.contains(_.pluck(self.get("messages"), 'id'), m.id) ; });
        // escape the message content and set the timezone
        _.map(messages, function(m){
            if(!m.from_id){
                m.from_id = [false, self.get_anonymous_name()];
            }
            //m.body = self.escape_keep_url(m.body);
            m.body = mail_utils.apply_shortcode(m.body, self.options.emoji);
            m.create_date = moment(time.str_to_datetime(m.create_date)).format('YYYY-MM-DD HH:mm:ss');
            return m;
        });
        this.set("messages", _.sortBy(this.get("messages").concat(messages), function(m){ return m.id; }));
    },
    render_messages: function(){
        var self = this;
        /* TODO JEM recreate a preprocess */
        var res = {};
        var last_date_day, last_user_id = -1;
        _.each(this.get("messages"), function(current){
            // add the url of the avatar for all users in the conversation
            current.from_id[2] = session.url(_.str.sprintf("/im_chat/image/%s/%s", self.get('session').uuid, current.author_id[0]));
            var date_day = current.date.split(" ")[0];
            if(date_day !== last_date_day){
                res[date_day] = [];
                last_user_id = -1;
            }
            last_date_day = date_day;

            if(current.message_type == "comment"){ // traditionnal message
                if(last_user_id === current.author_id[0]){
                    _.last(res[date_day]).push(current);
                }else{
                    res[date_day].push([current]);
                }
                last_user_id = current.author_id[0];
            }else{ // meta message
                res[date_day].push([current]);
                last_user_id = -1;
            }

        });
        // render and set the content of the chatview
        // TODO jem : when refactoring this, don't forget to pre-process date in this function before render quweb template
        // since, moment will not be define in qweb on the website pages, because the helper (see csn) is in core.js and cannot be
        // imported in the frontend.
        var m_content = $(QWeb.render("im_chat.Conversation_content", {"list": res}));
        this.$('.oe_im_chatview_content_bubbles').html(m_content);
        this._go_bottom();
    },
    // utils and event
    get_anonymous_name: function(){
        var name = this.options["defaultUsername"];
        _.each(this.get('session').partners, function(u){
            if(!u.id){
                name = u.name;
            }
        });
        return name;
    },
    keydown: function(e) {
        if(e && e.which == 27) {
            if(this.$el.prev().find('.oe_im_chatview_input').length > 0){
                this.$el.prev().find('.oe_im_chatview_input').focus();
            }else{
                this.$el.next().find('.oe_im_chatview_input').focus();
            }
            e.stopPropagation();
            this.session_update_state('closed');
        }
        if(e && e.which !== 13) {
            return;
        }
        var mes = this.$("input").val();
        if (! mes.trim()) {
            return;
        }
        this.$("input").val("");
        this.message_send(mes);
    },
    _go_bottom: function() {
        this.$(".oe_im_chatview_content").scrollTop(this.$(".oe_im_chatview_content").get(0).scrollHeight);
    },
    focus: function() {
        this.$(".oe_im_chatview_input").focus();
    },
    click_header: function(event){
        var classes = event.target.className.split(' ');
        if(_.contains(classes, 'header_name') || _.contains(classes, 'oe_im_chatview_header')){
            this.session_update_state();
        }
    },
    click_close: function(event) {
        this.session_update_state('closed');
    },
    destroy: function() {
        this.trigger("destroyed", this.get('session').id);
        return this._super();
    }
});


return {
    Conversation: Conversation,
    ConversationManager: ConversationManager,
};

});
