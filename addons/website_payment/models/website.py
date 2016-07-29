from openerp import api, models


class Website(models.Model):
    _inherit = "website"

    @api.model
    def payment_acquirers(self):
        return list(self.env['payment.acquirer'].search([('website_published', '=', True)]))
