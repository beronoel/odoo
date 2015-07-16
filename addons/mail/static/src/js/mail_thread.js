odoo.define('mail.thread', function (require) {
"use strict";

var core = require('web.core');
var data = require('web.data');
var Widget = require('web.Widget');
var session = require('web.session');
var web_client = require('web.web_client');
var mail_utils = require('mail.utils');

var _t = core._t;
var QWeb = core.qweb;


var LIMIT_MESSAGE = 20;

/**
 * Widget : Input textbox to post messages
 *
 * Input with 2 buttons to manage attachment and emoji
 *      - Attachment : upload selected attachment (one at a time) and display them below the textbox. Prevent
          posting message while uploading
 *      - Emoji : popover exposing emoji list, and append emoji shortcode to the textbox when click on emoji image
 **/
var MailComposeMessage = Widget.extend({
    template: 'mail.ComposeMessage',
    events: {
        "keydown .o_mail_compose_message_input": "on_keydown",
        "change input.oe_form_binary_file": "on_attachment_change",
        "click .o_mail_compose_message_attachment_list .o_mail_attachment_delete": "on_attachment_delete",
        "click .o_mail_compose_message_button_attachment": 'on_click_attachment',
    },
    init: function(parent, dataset, options){
        this._super.apply(this, arguments);
        this.thread_dataset = dataset;
        this.emoji_list = options.emoji_list || {};
        this.context = options.context || {};
        // attachment handeling
        this.AttachmentDataSet = new data.DataSetSearch(this, 'ir.attachment', this.context);
        this.fileupload_id = _.uniqueId('o_mail_chat_fileupload');
        this.set('attachment_ids', []);
    },
    start: function(){
        var self = this;
        this.$input = this.$('.o_mail_compose_message_input');
        this.$attachment_button = this.$(".o_mail_compose_message_button_attachment");
        // attachments
        $(window).on(this.fileupload_id, this.on_attachment_loaded);
        this.on("change:attachment_ids", this, this.attachment_render);
        // emoji
        self.$('.o_mail_compose_message_button_emoji').popover({
            placement: 'top',
            content: function(){
                if(!self.$emoji){ // lazy rendering
                    self.$emoji = $(QWeb.render('mail.ComposeMessage.emoji', {'widget': self}));
                    self.$emoji.find('.o_mail_compose_message_emoji_img').on('click', self, self.on_click_emoji_img);
                }
                return self.$emoji
            },
            html: true,
            container: '.o_mail_compose_message_emoji',
            trigger: 'focus',
        });
        return this._super();
    },
    // events
    on_click_attachment: function(event){
        console.log('on_click_attachment');
        event.preventDefault();
        this.$('input.oe_form_binary_file').click();
    },
    on_click_emoji_img: function(event){
        this.$input.val(this.$input.val() + " " + $(event.currentTarget).data('emoji')+ " ");
        this.$input.focus();
    },
    on_keydown: function(event){
        if(event && event.which !== 13) {
            return;
        }
        var $input = this.$(event.currentTarget);
        var mes = $input.val();
        if (! mes.trim() && this.do_check_attachment_upload()) {
            return;
        }
        $input.val("");
        console.log('mes', mes);
        this.message_post(mes, _.pluck(this.get('attachment_ids'), 'id'));
    },
    // message post
    message_post: function(body, attachment_ids, kwargs){
        var self = this;
        kwargs = kwargs || {};
        var values = _.extend(kwargs, {
            'body': body,
            'attachment_ids': attachment_ids,
        });
        return this.thread_dataset._model.call('message_post', [this.context.default_res_id], values).then(function(message_id){
            self.clean_attachments(); // empty attachment list
            self.trigger('message_sent', message_id);
            return message_id;
        });
    },
    // attachment business
    on_attachment_change: function(event){
        var $target = $(event.target);
        if ($target.val() !== '') {
            var filename = $target.val().replace(/.*[\\\/]/,'');
            // if the files exits for this answer, delete the file before upload
            var attachments = [];
            for (var i in this.get('attachment_ids')) {
                if ((this.get('attachment_ids')[i].filename || this.get('attachment_ids')[i].name) == filename) {
                    if (this.get('attachment_ids')[i].upload) {
                        return false;
                    }
                    this.AttachmentDataSet.unlink([this.get('attachment_ids')[i].id]);
                } else {
                    attachments.push(this.get('attachment_ids')[i]);
                }
            }
            // submit filename
            this.$('form.oe_form_binary_form').submit();
            this.$attachment_button.prop('disabled', true);

            attachments.push({
                'id': 0,
                'name': filename,
                'filename': filename,
                'url': '',
                'upload': true
            });
            this.set('attachment_ids', attachments);
        }
    },
    on_attachment_loaded: function(event, result){
        var attachment_ids = [];
        if (result.error || !result.id ) {
            this.do_warn(result.error);
            attachment_ids = _.filter(this.get('attachment_ids'), function (val) { return !val.upload; });
        }else{
            _.each(this.get('attachment_ids'), function(a){
                if (a.filename == result.filename && a.upload) {
                    attachment_ids.push({
                        'id': result.id,
                        'name': result.name,
                        'filename': result.filename,
                        'url': session.url('/web/binary/saveas', {model: 'ir.attachment', field: 'datas', filename_field: 'name', 'id': result.id}),
                    });
                }else{
                    attachment_ids.push(a);
                }
            });
        }
        this.set('attachment_ids', attachment_ids);

        // TODO JEM : understand the 2 lines below ....
        var $input = this.$('input.oe_form_binary_file');
        $input.after($input.clone(true)).remove();

        this.$attachment_button.prop('disabled', false);
    },
    on_attachment_delete: function(event){
        console.log('on_attachment_delete'); // TODO JEM : check if correct
        event.stopPropagation();
        var attachment_id = $(event.target).data("id");
        if (attachment_id) {
            var attachments = [];
            for (var i in this.attachment_ids) {
                if (attachment_id != this.attachment_ids[i].id) {
                    attachments.push(this.attachment_ids[i]);
                }
                else {
                    this.AttachmentDataSet.unlink([attachment_id]);
                }
            }
            this.set('attachment_ids', attachments);
        }
    },
    do_check_attachment_upload: function () {
        if (_.find(this.get('attachment_ids'), function (file) {return file.upload;})) {
            this.do_warn(_t("Uploading error"), _t("Please, wait while the file is uploading."));
            return false;
        }
        return true;
    },
    clean_attachments: function(){
        this.set('attachment_ids', []);
    },
    // ui
    attachment_render: function(){
        this.$('.o_mail_compose_message_attachment_list').html(QWeb.render('mail.ComposeMessage.attachments', {'widget': this}));
    },
});


/**
 * Mail Thread Mixin : Messages Managment
 *
 * Load, Fetch, Display mail.message
 * This is a mixin since it will be inherit by a form_common.AbstractField and a Wigdet (Client Action);
 **/
var MailThreadMixin = {
    init: function(){
        this.MessageDatasetSearch = new data.DataSetSearch(this, 'mail.message');
        this.set('messages', []);
        this.partner_id = session.partner_id || false;
        this.emoji_substitution = {};
    },
    start: function(){
        this.on("change:messages", this, this.message_render);
    },
    // Common Actions (They should be bind on the implementing widget, the 'events' dict)
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
    // Message functions
    /**
     * Fetch given message
     * @param Array() : list of mail.message identifiers to fetch
     * @returns {Deferred} resolved when the messages are loaded
     */
    message_format: function(message_ids){
        return this.MessageDatasetSearch._model.call('message_format', [message_ids]);
    },
    /**
     * Fetch mail.message in the format defined server side
     * @param domain : Odoo Domain of the message to fetch
     * @returns {Deferred} resolved when the messages are loaded
     */
    message_fetch: function(domain, limit){
        domain = domain || this.get_message_domain();
        limit = limit || LIMIT_MESSAGE;
        return this._message_fetch(domain, limit);
    },
    _message_fetch: function(domain, limit){
        return this.MessageDatasetSearch._model.call('message_fetch', [domain], {limit: limit});
    },
    message_insert: function(messages){
        var current_messages = this.get('messages');
        current_messages = current_messages.concat(messages);
        this.set('messages', this._message_preprocess(current_messages));
    },
    /**
     * Preprocess the list of messages before rendering, add 'computed' field (is_needaction,
     * is_starred, ...), and apply image shortcode to the message body.
     * @param messages : list of mail.message (formatted)
     * @returns list of messages. It can be sorted, grouped, ...
     */
    _message_preprocess: function(messages){
        var self = this;
        _.each(messages, function(m){
            m.is_neeadaction = _.contains(m.needaction_partner_ids, self.partner_id);
            m.is_starred = _.contains(m.starred_partner_ids, self.partner_id);
            if(m.body){
                m.body = mail_utils.apply_shortcode(m.body, self.emoji_substitution);
            }
            _.each(m.attachment_ids, function(a){
                a.url = session.url('/web/binary/saveas', {model: 'ir.attachment', field: 'datas', filename_field: 'name', 'id': a.id});
            });
        });
        return _.sortBy(messages, 'date');
    },
    /**
     * Take the current messages, render them, and insert the rendering in the DOM.
     * This is triggered when the mesasge list change.
     * Must be redefines, since it depends on the complete DOM widget
     */
    message_render: function(){

    },
    // Message Domains
    get_message_domain: function(){
        return [];
    },
    get_message_domain_history: function(){
        return this.get_message_domain().concat([['id', '<', _.min(_.pluck(this.get('messages'), 'id'))]]);
    },
    // Others
    /**
     * Set the list of emoji to be substituted in message body
     * @param emoji_list : list of emoji Object
     */
    emoji_set_substitution: function(emoji_list){
        var emoji_substitution = {};
        _.each(emoji_list, function(emoji){
            emoji_substitution[emoji.source] = emoji.substitution;
        });
        this.emoji_substitution = emoji_substitution;
    },
};


return {
    MailComposeMessage: MailComposeMessage,
    MailThreadMixin: MailThreadMixin,
    LIMIT_MESSAGE: LIMIT_MESSAGE,
}


});
