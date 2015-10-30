# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.exceptions import UserError, ValidationError
from openerp import api, fields, models, _


class ProcurementRule(models.Model):
    '''
    A rule describe what a procurement should do; produce, buy, move, ...
    '''
    _inherit = 'procurement.rule'

    do_stop = fields.Boolean('Manual Decision')


class ProcurementOrder(models.Model):
    """
    Procurement Orders
    """
    _inherit = "procurement.order"

    do_stop = fields.Boolean('Manual Decision', help="If you decide to do stop, it will not be run by the schedulers and you have to run manually", default=False)

    @api.model
    def _run(self, procurement):
        if procurement.do_stop:
            return False

    @api.multi
    def run_continue(self):
        self.write({'do_stop': False})
        self.run()

    @api.model
    def _assign(self, procurement):
        '''This method check what to do with the given procurement in order to complete its needs.
        It returns False if no solution is found, otherwise it stores the matching rule (if any) and
        returns True.
            :param procurement: browse record
            :rtype: boolean
        '''
        #if the procurement already has a rule assigned, we keep it (it has a higher priority as it may have been chosen manually)
        procurement_had_no_rule = not procurement.rule_id.id
        res = super(ProcurementOrder, self)._assign(procurement)
        if procurement.rule_id.do_stop and (procurement_had_no_rule or procurement.do_stop):
            procurement.do_stop = True
            return False
        return res