# coding: utf-8

from authorize_request import AuthhorizeRequest
from datetime import datetime
import hashlib
import hmac
import logging
import time
import urlparse

from odoo import api, fields, models
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_authorize.controllers.main import AuthorizeController
from odoo.tools.float_utils import float_compare
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class PaymentAcquirerAuthorize(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('authorize', 'Authorize.Net')])
    authorize_login = fields.Char(string='API Login Id', required_if_provider='authorize')
    authorize_transaction_key = fields.Char(string='API Transaction Key', required_if_provider='authorize')

    def _get_authorize_urls(self, environment):
        """ Authorize URLs """
        if environment == 'prod':
            return {'authorize_form_url': 'https://secure2.authorize.net/gateway/transact.dll'}
        else:
            return {'authorize_form_url': 'https://test.authorize.net/gateway/transact.dll'}

    def _authorize_generate_hashing(self, values):
        data = '^'.join([
            values['x_login'],
            values['x_fp_sequence'],
            values['x_fp_timestamp'],
            values['x_amount'],
            values['x_currency_code']])
        return hmac.new(str(values['x_trans_key']), data, hashlib.md5).hexdigest()

    @api.multi
    def authorize_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        authorize_tx_values = dict(values)
        temp_authorize_tx_values = {
            'x_login': self.authorize_login,
            'x_trans_key': self.authorize_transaction_key,
            'x_amount': str(values['amount']),
            'x_show_form': 'PAYMENT_FORM',
            'x_type': 'AUTH_CAPTURE',
            'x_method': 'CC',
            'x_fp_sequence': '%s%s' % (self.id, int(time.time())),
            'x_version': '3.1',
            'x_relay_response': 'TRUE',
            'x_fp_timestamp': str(int(time.time())),
            'x_relay_url': '%s' % urlparse.urljoin(base_url, AuthorizeController._return_url),
            'x_cancel_url': '%s' % urlparse.urljoin(base_url, AuthorizeController._cancel_url),
            'x_currency_code': values['currency'] and values['currency'].name or '',
            'address': values.get('partner_address'),
            'city': values.get('partner_city'),
            'country': values.get('partner_country') and values.get('partner_country').name or '',
            'email': values.get('partner_email'),
            'zip_code': values.get('partner_zip'),
            'first_name': values.get('partner_first_name'),
            'last_name': values.get('partner_last_name'),
            'phone': values.get('partner_phone'),
            'state': values.get('partner_state') and values['partner_state'].code or '',
            'billing_address': values.get('billing_partner_address'),
            'billing_city': values.get('billing_partner_city'),
            'billing_country': values.get('billing_partner_country') and values.get('billing_partner_country').name or '',
            'billing_email': values.get('billing_partner_email'),
            'billing_zip_code': values.get('billing_partner_zip'),
            'billing_first_name': values.get('billing_partner_first_name'),
            'billing_last_name': values.get('billing_partner_last_name'),
            'billing_phone': values.get('billing_partner_phone'),
            'billing_state': values.get('billing_partner_state') and values['billing_partner_state'].code or '',
        }
        temp_authorize_tx_values['returndata'] = authorize_tx_values.pop('return_url', '')
        temp_authorize_tx_values['x_fp_hash'] = self._authorize_generate_hashing(temp_authorize_tx_values)
        authorize_tx_values.update(temp_authorize_tx_values)
        return authorize_tx_values

    @api.multi
    def authorize_get_form_action_url(self):
        self.ensure_one()
        return self._get_authorize_urls(self.environment)['authorize_form_url']

    @api.model
    def authorize_s2s_form_process(self, data):
        values = {
            'cc_number': data.get('cc_number'),
            'cc_holder_name': data.get('cc_holder_name'),
            'cc_expiry': data.get('cc_expiry'),
            'cc_cvc': data.get('cc_cvc'),
            'cc_brand': data.get('cc_brand'),
            'acquirer_id': int(data.get('acquirer_id')),
            'partner_id': int(data.get('partner_id'))
        }
        PaymentMethod = self.env['payment.token'].sudo().create(values)
        return PaymentMethod.id

    @api.multi
    def authorize_s2s_form_validate(self, data):
        error = dict()
        mandatory_fields = ["cc_number", "cc_cvc", "cc_holder_name", "cc_expiry", "cc_brand"]
        # Validation
        for field_name in mandatory_fields:
            if not data.get(field_name):
                error[field_name] = 'missing'
        if data['cc_expiry'] and datetime.now().strftime('%y%M') > datetime.strptime(data['cc_expiry'], '%M / %y').strftime('%y%M'):
            return False
        return False if error else True


class TxAuthorize(models.Model):
    _inherit = 'payment.transaction'

    _authorize_valid_tx_status = 1
    _authorize_pending_tx_status = 4
    _authorize_cancel_tx_status = 2

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _authorize_form_get_tx_from_data(self, data):
        """ Given a data dict coming from authorize, verify it and find the related
        transaction record. """
        reference, trans_id, fingerprint = data.get('x_invoice_num'), data.get('x_trans_id'), data.get('x_MD5_Hash')
        if not reference or not trans_id or not fingerprint:
            error_msg = 'Authorize: received data with missing reference (%s) or trans_id (%s) or fingerprint (%s)' % (reference, trans_id, fingerprint)
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        tx = self.search([('reference', '=', reference)])
        if not tx or len(tx) > 1:
            error_msg = 'Authorize: received data for reference %s' % (reference)
            if not tx:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return tx[0]

    @api.multi
    def _authorize_form_get_invalid_parameters(self, data):
        invalid_parameters = []

        if self.acquirer_reference and data.get('x_trans_id') != self.acquirer_reference:
            invalid_parameters.append(('Transaction Id', data.get('x_trans_id'), self.acquirer_reference))
        # check what is buyed
        if float_compare(float(data.get('x_amount', '0.0')), self.amount, 2) != 0:
            invalid_parameters.append(('Amount', data.get('x_amount'), '%.2f' % self.amount))
        return invalid_parameters

    @api.multi
    def _authorize_form_validate(self, data):
        if self.state == 'done':
            _logger.warning('Authorize: trying to validate an already validated tx (ref %s)' % self.reference)
            return True
        status_code = int(data.get('x_response_code', '0'))
        if status_code == self._authorize_valid_tx_status:
            self.write({
                'state': 'done',
                'acquirer_reference': data.get('x_trans_id'),
            })
            return True
        elif status_code == self._authorize_pending_tx_status:
            self.write({
                'state': 'pending',
                'acquirer_reference': data.get('x_trans_id'),
            })
            return True
        elif status_code == self._authorize_cancel_tx_status:
            self.write({
                'state': 'cancel',
                'acquirer_reference': data.get('x_trans_id'),
            })
            return True
        else:
            error = data.get('x_response_reason_text')
            _logger.info(error)
            self.write({
                'state': 'error',
                'state_message': error,
                'acquirer_reference': data.get('x_trans_id'),
            })
            return False

    @api.multi
    def authorize_s2s_do_transaction(self, **data):
        self.ensure_one()
        transaction = AuthhorizeRequest(self.acquirer_id.environment, self.acquirer_id.authorize_login, self.acquirer_id.authorize_transaction_key)
        tree = transaction.create_authorize_s2s_transaction(self.payment_token_id.acquirer_ref, self.payment_token_id.authorize_payment_id, self.amount, str(self.reference))
        return self._authorize_s2s_validate_tree(tree)

    @api.multi
    def _authorize_s2s_validate_tree(self, tree):
        return self._authorize_s2s_validate(tree)

    @api.multi
    def _authorize_s2s_validate(self, tree):
        self.ensure_one()
        if self.state == 'done':
            _logger.warning('Authorize: trying to validate an already validated tx (ref %s)' % self.reference)
            return True
        status_code = int(tree.get('x_response_code', '0'))
        if status_code == self._authorize_valid_tx_status:
            self.write({
                'state': 'done',
                'acquirer_reference': tree.get('x_trans_id'),
            })
            if self.callback_eval:
                safe_eval(self.callback_eval, {'self': self})
            return True
        elif status_code == self._authorize_pending_tx_status:
            self.write({
                'state': 'pending',
                'acquirer_reference': tree.get('x_trans_id'),
            })
            return True
        elif status_code == self._authorize_cancel_tx_status:
            self.write({
                'state': 'cancel',
                'acquirer_reference': tree.get('x_trans_id'),
            })
            return True
        else:
            error = tree.get('x_response_reason_text')
            _logger.info(error)
            self.write({
                'state': 'error',
                'state_message': error,
                'acquirer_reference': tree.get('x_trans_id'),
            })
            return False


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    authorize_payment_id = fields.Char(string='Authorize Payment Reference')

    @api.model
    def authorize_create(self, values):
        if values.get('cc_number'):
            values['cc_number'] = values['cc_number'].replace(' ', '')
            acquirer = self.env['payment.acquirer'].browse(values['acquirer_id'])
            expiry = str(values['cc_expiry'][:2]) + str(values['cc_expiry'][-2:])
            customer = AuthhorizeRequest(acquirer.environment, acquirer.authorize_login, acquirer.authorize_transaction_key)
            payments = customer.create_authorize_s2s_payment(values['cc_number'], expiry)
            profile_id, payment_id = customer.create_authorize_s2s_profile([payments], self.env.user.partner_id.email)
            if payment_id and profile_id:
                return {
                    'acquirer_ref': profile_id,
                    'name': 'XXXXXXXXXXXX%s - %s' % (values['cc_number'][-4:], values['cc_holder_name']),
                    'authorize_payment_id': payment_id[0]
                }
        return {}
