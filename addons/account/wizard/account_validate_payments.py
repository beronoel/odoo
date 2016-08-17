from openerp import models, api, _
from openerp.exceptions import UserError


class ValidatePayment(models.TransientModel):
    _name = "validate.payment"
    _description = "Validate Payments"

    @api.multi
    def validate_payment(self):
        context = dict(self._context or {})
        payments = self.env['account.payment'].browse(context.get('active_ids'))
        payments_to_post = self.env['account.payment']
        for payment in payments:
            if payment.state == 'draft':
                payments_to_post += payment
        if not payments_to_post:
            raise UserError(_('There is no journal items in draft state to post.'))
        payments_to_post.post()
        return {'type': 'ir.actions.act_window_close'}
