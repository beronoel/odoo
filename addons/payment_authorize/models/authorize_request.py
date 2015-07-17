# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
from suds.client import Client
from suds import WebFault
from ssl import SSLError
import urllib
from uuid import uuid4

_logger = logging.getLogger(__name__)
logging.getLogger('suds.client').setLevel(logging.DEBUG)

RESPONSE_FIELDS = {
    0: 'x_response_code',
    2: 'x_response_reason_code',
    3: 'x_response_reason_text',
    4: 'x_authorization_code',
    5: 'x_avs_response',
    6: 'x_trans_id',
    7: 'x_invoice_num',
    9: 'x_amount',
}

class AuthhorizeRequest():

    def __init__(self, environment, login_id, transaction_key):
        if environment == 'prod':
            authorize_s2s_url = 'https://api.authorize.net/soap/v1/Service.asmx?WSDL'
        else:
            authorize_s2s_url = 'https://apitest.authorize.net/soap/v1/Service.asmx?WSDL'
        self.login_id = login_id
        self.transaction_key = transaction_key
        self.transaction_options = urllib.urlencode({
            'x_version': '3.1',
            'x_test_request': 'Y' if environment == 'test' else 'F',
            'x_delim_data': 'TRUE',
            'x_delim_char': ';',
        })
        self.start_payment(authorize_s2s_url)
        self.authorize_s2s_client_auth()

    def start_payment(self, authorize_s2s_url):
        self.client = Client(authorize_s2s_url)

    def authorize_s2s_client_auth(self):
        self.client_auth = self.client.factory.create('MerchantAuthenticationType')
        self.client_auth.name = self.login_id
        self.client_auth.transactionKey = self.transaction_key

    def _authorize_s2s_call_service(self, service, *args):
        method = getattr(self.client.service, service)
        try:
            response = method(self.client_auth, *args)
        except (WebFault, SSLError) as e:
            raise e
        return response

    def create_authorize_s2s_payment(self, card_number=None, expiration_date=None, card_code=None):
        payment_profile = self.client.factory.create('CustomerPaymentProfileType')
        customer_type_enum = self.client.factory.create('CustomerTypeEnum')
        payment_profile.customerType = customer_type_enum.individual
        payment_type = self.client.factory.create('PaymentType')
        credit_card_type = self.client.factory.create('CreditCardType')
        credit_card_type.cardNumber = card_number
        credit_card_type.expirationDate = expiration_date
        credit_card_type.cardCode = card_code
        payment_type.creditCard = credit_card_type
        payment_profile.payment = payment_type
        return payment_profile

    def create_authorize_s2s_profile(self, payments=None, email=None):
        profile = self.client.factory.create('CustomerProfileType')
        profile.merchantCustomerId = uuid4().hex[:20]
        profile.email = email
        if payments:
            payment_array = self.client.factory.create('ArrayOfCustomerPaymentProfileType')
            payment_array.CustomerPaymentProfileType = payments
            profile.paymentProfiles = payment_array
        response = self._authorize_s2s_call_service('CreateCustomerProfile', profile, 'none')
        profile_id = response.customerProfileId
        payment_ids = None
        if response.resultCode == 'Ok':
            payment_ids = response.customerPaymentProfileIdList[0]
        return profile_id, payment_ids

    def parse_authorize_s2s_response(self, response):
        response = response.split(';')
        return {name : response[index] for index, name in RESPONSE_FIELDS.items()}

    def create_authorize_s2s_transaction(self, profile_id, payment_id, amount, invoice_number):
        transaction = self.client.factory.create('ProfileTransactionType')
        capture = self.client.factory.create('ProfileTransAuthCaptureType')
        capture.amount = str(amount)
        capture.customerProfileId = profile_id
        capture.customerPaymentProfileId = payment_id
        capture.order.invoiceNumber = invoice_number
        transaction.profileTransAuthCapture = capture
        response = self._authorize_s2s_call_service('CreateCustomerProfileTransaction',
            transaction, self.transaction_options)
        return self.parse_authorize_s2s_response(response.directResponse)
