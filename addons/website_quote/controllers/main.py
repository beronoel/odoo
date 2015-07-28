# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import werkzeug

from openerp import fields, http, _
from openerp.http import request

class SaleQuote(http.Controller):
    @http.route([
        "/quote/<int:order_id>",
        "/quote/<int:order_id>/<token>"
    ], type='http', auth="public", website=True)
    def view(self, order_id, token=None, pdf=None, message=False, **post):
        # use SUPERUSER_ID allow to access/view order for public user
        # only if he knows the private token
        SaleOrder = request.env['sale.order']
        now = fields.Date.from_string(fields.Date.today())
        return_url = '/quote/%s' % order_id
        if token:
            order = SaleOrder.sudo().search([('id', '=', order_id), ('access_token', '=', token)])
            # Log only once a day
            if request.session.get('view_quote', False) != now:
                request.session['view_quote'] = now
                body = _('Quotation viewed by customer')
                self.__message_post(body, order, message_type='comment')
            return_url += '/%s' % token
        else:
            order = SaleOrder.browse(order_id)
        action_id = request.env.ref('sale.action_quotations').id
        if not order:
            return request.website.render('website.404')
        days = 0
        if order.validity_date:
            days = (fields.Datetime.from_string(order.validity_date) - fields.Datetime.from_string(fields.Datetime.now())).days + 1
        if pdf:
            pdf = request.env['report'].sudo().get_pdf(order, 'website_quote.report_quote')
            pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
            return request.make_response(pdf, headers=pdfhttpheaders)
        payment_transaction = request.env['payment.transaction'].sudo().search([('reference', '=', order.name)])
        values = {
            'quotation': order,
            'message': message and int(message) or False,
            'option': bool(order.options.filtered(lambda x: not x.line_id)),
            'order_valid': (not order.validity_date) or (now <= fields.Date.from_string(order.validity_date)),
            'days_valid': max(days, 0),
            'action': action_id,
            'tx_id': payment_transaction.id,
            'tx_state': payment_transaction.state,
            'tx_post_msg': payment_transaction.acquirer_id.post_msg,
            'need_payment': not payment_transaction and order.state == 'manual'
        }

        if order.require_payment or (not payment_transaction and order.state == 'manual'):
            PaymentAcquirer = request.env['payment.acquirer']
            values['acquirers'] = list(PaymentAcquirer.search([('website_published', '=', True), ('company_id', '=', order.company_id.id)]))
            render_ctx = dict(request.env.context, submit_class='btn btn-primary', submit_txt=_('Pay & Confirm'))
            for acquirer in values['acquirers']:
                acquirer.button = acquirer.with_context(render_ctx).sudo().render(
                    order.name,
                    order.amount_total,
                    order.pricelist_id.currency_id.id,
                    partner_id=order.partner_id.id,
                    tx_values={
                        'return_url': return_url,
                        'type': 'form',
                        'alias_usage': _('If we store your payment information on our server, subscription payments will be made automatically.')
                    })
        return request.website.render('website_quote.so_quotation', values)

    @http.route(['/quote/accept'], type='json', auth="public", website=True)
    def accept(self, order_id, token=None, signer=None, sign=None, **post):
        order_sudo = request.env['sale.order'].sudo().search([('id', '=', int(order_id)), ('access_token', '=', token), ('require_payment', '=', False)])
        if not order_sudo:
            return request.website.render('website.404')
        attachments = sign and [('signature.png', sign.decode('base64'))] or []
        order_sudo.action_button_confirm()
        message = _('Order signed by %s') % (signer,)
        self.__message_post(message, order_sudo, message_type='comment', subtype='mt_comment', attachments=attachments)
        return True

    @http.route(['/quote/<int:order_id>/<token>/decline'], type='http', auth="public", website=True)
    def decline(self, order_id, token, **post):
        order_sudo = request.env['sale.order'].sudo().search([('id', '=', order_id), ('access_token', '=', token)])
        if not order_sudo:
            return request.website.render('website.404')
        order_sudo.action_cancel()
        message = post.get('decline_message')
        if message:
            self.__message_post(message, order_sudo, message_type='comment', subtype='mt_comment')
        return werkzeug.utils.redirect("/quote/%s/%s?message=2" % (order_id, token))

    @http.route(['/quote/<int:order_id>/<token>/post'], type='http', auth="public", website=True)
    def post(self, order_id, token, **post):
        # use SUPERUSER_ID allow to access/view order for public user
        order_sudo = request.env['sale.order'].sudo().search([('id', '=', order_id), ('access_token', '=', token)])
        message = post.get('comment')
        if not order_sudo:
            return request.website.render('website.404')
        if message:
            self.__message_post(message, order_sudo, message_type='comment', subtype='mt_comment')
        return werkzeug.utils.redirect("/quote/%s/%s?message=1" % (order_id, token))

    def __message_post(self, message, order, message_type='comment', subtype=False, attachments=[]):
        request.session.body = message
        user_sudo = request.env.user.sudo()
        if 'body' in request.session and request.session.body:
            order.sudo().message_post(body=request.session.body, message_type=message_type,
                    subtype=subtype, author_id=user_sudo.partner_id.id, attachments=attachments)
            request.session.body = False
        return True

    @http.route(['/quote/update_line'], type='json', auth="public", website=True)
    def update(self, line_id, remove=False, unlink=False, order_id=None, token=None, **post):
        order_id = int(order_id)
        order_sudo = request.env['sale.order'].sudo().search([('id', '=', order_id), ('access_token', '=', token)])
        if not order_sudo:
            return request.website.render('website.404')
        if order_sudo.state not in ('draft', 'sent'):
            return False
        line_id = int(line_id)
        if unlink:
            request.env['sale.order.line'].search([('id', '=', line_id), ('order_id', '=', order_id)]).sudo().unlink()
            return False
        number = (remove and -1 or 1)
        order_line = request.env['sale.order.line'].sudo().browse(line_id)
        order_line.product_uom_qty += number
        return [str(order_line.product_uom_qty), str(order_sudo.amount_total)]

    @http.route(["/quote/template/<model('sale.quote.template'):quote>"], type='http', auth="user", website=True)
    def template_view(self, quote, **post):
        values = {'template': quote}
        return request.website.render('website_quote.so_template', values)

    @http.route(["/quote/add_line/<int:option_id>/<int:order_id>/<token>"], type='http', auth="public", website=True)
    def add(self, option_id, order_id, token, **post):
        vals = {}
        order_sudo = request.env['sale.order'].sudo().search([('id', '=', order_id), ('access_token', '=', token)])
        if not order_sudo:
            return request.website.render('website.404')
        if order_sudo.state not in ['draft', 'sent']:
            return request.website.render('website.http_error', {'status_code': 'Forbidden', 'status_message': _('You cannot add options to a confirmed order.')})
        option_sudo = request.env['sale.order.option'].sudo().browse(option_id)

        result = request.env['sale.order.line'].browse(order_id).sudo().product_id_change(
            False, option_sudo.product_id.id, option_sudo.quantity, option_sudo.uom_id.id, option_sudo.quantity, option_sudo.uom_id.id,
            option_sudo.name, order_sudo.partner_id.id, False, True, fields.Date.today(),
            False, order_sudo.fiscal_position_id.id, True)
        vals = result.get('value', {})
        if 'tax_id' in vals:
            vals['tax_id'] = [(6, 0, vals['tax_id'])]

        vals.update({
            'price_unit': option_sudo.price_unit,
            'website_description': option_sudo.website_description,
            'name': option_sudo.name,
            'order_id': order_sudo.id,
            'product_id': option_sudo.product_id.id,
            'product_uos_qty': option_sudo.quantity,
            'product_uos': option_sudo.uom_id.id,
            'product_uom_qty': option_sudo.quantity,
            'product_uom': option_sudo.uom_id.id,
            'discount': option_sudo.discount,
        })
        order_line = request.env['sale.order.line'].sudo().create(vals)
        option_sudo.line_id = order_line.id
        return werkzeug.utils.redirect("/quote/%s/%s#pricing" % (order_sudo.id, token))

    # note dbo: website_sale code
    @http.route(['/quote/<int:order_id>/transaction/<int:acquirer_id>'], type='json', auth="public", website=True)
    def payment_transaction(self, acquirer_id, order_id):
        """ Json method that creates a payment.transaction, used to create a
        transaction when the user clicks on 'pay now' button. After having
        created the transaction, the event continues and the user is redirected
        to the acquirer website.

        :param int acquirer_id: id of a payment.acquirer record. If not set the
                                user is redirected to the checkout page
        """
        PaymentTransaction = request.env['payment.transaction']
        order_sudo = request.env['sale.order'].sudo().browse(order_id)

        if not order_sudo or not order_sudo.order_line or acquirer_id is None:
            return request.redirect("/quote/" + str(order_id))

        # find an already existing transaction
        transaction_sudo = PaymentTransaction.sudo().search([('reference', '=', order_sudo.name)])
        if transaction_sudo:
            if transaction_sudo.state == 'draft':  # button cliked but no more info -> rewrite on tx or create a new one ?
                transaction_sudo.acquirer_id = acquirer_id
            transaction_id = transaction_sudo.id
        else:
            transaction_sudo = PaymentTransaction.sudo().create({
                'acquirer_id': acquirer_id,
                'type': 'form',
                'amount': order_sudo.amount_total,
                'currency_id': order_sudo.pricelist_id.currency_id.id,
                'partner_id': order_sudo.partner_id.id,
                'partner_country_id': order_sudo.partner_id.country_id.id,
                'reference': order_sudo.name,
                'sale_order_id': order_sudo.id,
            })
            transaction_id = transaction_sudo.id
            request.session['sale_transaction_id'] = transaction_id

        # confirm the quotation
        if transaction_sudo.acquirer_id.auto_confirm == 'at_pay_now':
            order_sudo.action_button_confirm()

        return transaction_id
