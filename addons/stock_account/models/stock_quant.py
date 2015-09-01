# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from openerp import api, models

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.model
    def _get_inventory_value(self, quant):
        if quant.product_id.cost_method in ('real'):
            return quant.cost * quant.qty
        return super(StockQuant, self)._get_inventory_value(quant)

    @api.multi
    def _price_update(self, newprice):
        ''' This function is called at the end of negative quant reconciliation and does the accounting entries adjustemnts and the update of the product cost price if needed
        '''
        AccountMove = self.env['account.move']
        super(StockQuant, self)._price_update(newprice)
        for quant in self:
            move = self._get_latest_move(quant)
            valuation_update = newprice - quant.cost
            # this is where we post accounting entries for adjustment, if needed
            if not quant.company_id.currency_id.is_zero(valuation_update):
                # If neg quant period already closed (likely with manual valuation), skip update
                if AccountMove.browse(move.id)._check_lock_date():
                    self.with_context(force_valuation_amount=valuation_update)._account_entry_move([quant], move)

            #update the standard price of the product, only if we would have done it if we'd have had enough stock at first, which means
            #1) the product cost's method is 'real'
            #2) we just fixed a negative quant caused by an outgoing shipment
            if quant.product_id.cost_method == 'real' and quant.location_id.usage != 'internal':
                move._store_average_cost_price()

    def _account_entry_move(self, quants, move):
        """
        Accounting Valuation Entries

        quants: browse record list of Quants to create accounting valuation entries for. Unempty and all quants are supposed to have the same location id (thay already moved in)
        move: Move to use. browse record
        """
        StockLocation = self.env['stock.location']
        location_from = move.location_id
        location_to = quants[0].location_id
        company_from = StockLocation._location_owner(location_from)
        company_to = StockLocation._location_owner(location_to)

        if move.product_id.valuation != 'real_time':
            return False
        for q in quants:
            if q.owner_id:
                #if the quant isn't owned by the company, we don't make any valuation entry
                return False
            if q.qty <= 0:
                #we don't make any stock valuation for negative quants because the valuation is already made for the counterpart.
                #At that time the valuation will be made at the product cost price and afterward there will be new accounting entries
                #to make the adjustments when we know the real cost price.
                return False

        #in case of routes making the link between several warehouse of the same company, the transit location belongs to this company, so we don't need to create accounting entries
        # Create Journal Entry for products arriving in the company
        if company_to and (move.location_id.usage not in ('internal', 'transit') and move.location_dest_id.usage == 'internal' or company_from != company_to):
            journal_id, acc_src, acc_dest, acc_valuation = self.with_context(force_company=company_to.id)._get_accounting_data_for_valuation(move)
            if location_from and location_from.usage == 'customer':
                #goods returned from customer
                self.with_context(force_company=company_to.id)._create_account_move_line(quants, move, acc_dest, acc_valuation, journal_id)
            else:
                self.with_context(force_company=company_to.id)._create_account_move_line(quants, move, acc_src, acc_valuation, journal_id)

        # Create Journal Entry for products leaving the company
        if company_from and (move.location_id.usage == 'internal' and move.location_dest_id.usage not in ('internal', 'transit') or company_from != company_to):
            journal_id, acc_src, acc_dest, acc_valuation = self.with_context(force_company=company_from.id)._get_accounting_data_for_valuation(move)
            if location_to and location_to.usage == 'supplier':
                #goods returned to supplier
                self.with_context(force_company=company_from.id)._create_account_move_line(quants, move, acc_valuation, acc_src, journal_id)
            else:
                self.with_context(force_company=company_from.id)._create_account_move_line(quants, move, acc_valuation, acc_dest, journal_id)

    @api.model
    def _quant_create(self, qty, move, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False, force_location_from=False, force_location_to=False):
        quant = super(StockQuant, self)._quant_create(qty, move, lot_id=lot_id, owner_id=owner_id, src_package_id=src_package_id, dest_package_id=dest_package_id, force_location_from=force_location_from, force_location_to=force_location_to)
        if move.product_id.valuation == 'real_time':
            self._account_entry_move([quant], move)
        return quant

    @api.model
    def move_quants_write(self, quants, move, location_dest_id, dest_package_id, lot_id=False):
        res = super(StockQuant, self).move_quants_write(quants, move, location_dest_id, dest_package_id, lot_id=lot_id)
        if move.product_id.valuation == 'real_time':
            self._account_entry_move(quants, move)
        return res

    def _get_accounting_data_for_valuation(self, move):
        accounts = move.product_id.product_tmpl_id.get_product_accounts()
        if move.location_id.valuation_out_account_id:
            acc_src = move.location_id.valuation_out_account_id.id
        else:
            acc_src = accounts['stock_input'].id

        if move.location_dest_id.valuation_in_account_id:
            acc_dest = move.location_dest_id.valuation_in_account_id.id
        else:
            acc_dest = accounts['stock_output'].id

        acc_valuation = accounts.get('stock_valuation', False)
        if acc_valuation:
            acc_valuation = acc_valuation.id
        journal_id = accounts['stock_journal'].id
        return journal_id, acc_src, acc_dest, acc_valuation

    def _prepare_account_move_line(self, move, qty, cost, credit_account_id, debit_account_id):
        """
        Generate the account.move.line values to post to track the stock valuation difference due to the
        processing of the given quant.
        """
        if self.env.context.get('force_valuation_amount'):
            valuation_amount = self.env.context.get('force_valuation_amount')
        else:
            if move.product_id.cost_method == 'average':
                valuation_amount = cost if move.location_id.usage != 'internal' and move.location_dest_id.usage == 'internal' else move.product_id.standard_price
            else:
                valuation_amount = cost if move.product_id.cost_method == 'real' else move.product_id.standard_price
        #the standard_price of the product may be in another decimal precision, or not compatible with the coinage of
        #the company currency... so we need to use round() before creating the accounting entries.
        valuation_amount = move.company_id.currency_id.round(valuation_amount * qty)
        partner_id = (move.picking_id.partner_id and self.env['res.partner']._find_accounting_partner(move.picking_id.partner_id).id) or False
        debit_line_vals = {
            'name': move.name,
            'product_id': move.product_id.id,
            'quantity': qty,
            'product_uom_id': move.product_id.uom_id.id,
            'ref': move.picking_id and move.picking_id.name or False,
            'date': move.date,
            'partner_id': partner_id,
            'debit': valuation_amount > 0 and valuation_amount or 0,
            'credit': valuation_amount < 0 and -valuation_amount or 0,
            'account_id': debit_account_id,
        }
        credit_line_vals = {
            'name': move.name,
            'product_id': move.product_id.id,
            'quantity': qty,
            'product_uom_id': move.product_id.uom_id.id,
            'ref': move.picking_id and move.picking_id.name or False,
            'date': move.date,
            'partner_id': partner_id,
            'credit': valuation_amount > 0 and valuation_amount or 0,
            'debit': valuation_amount < 0 and -valuation_amount or 0,
            'account_id': credit_account_id,
        }
        return [(0, 0, debit_line_vals), (0, 0, credit_line_vals)]

    def _create_account_move_line(self, quants, move, credit_account_id, debit_account_id, journal_id):
        #group quants by cost
        quant_cost_qty = {}
        for quant in quants:
            if quant_cost_qty.get(quant.cost):
                quant_cost_qty[quant.cost] += quant.qty
            else:
                quant_cost_qty[quant.cost] = quant.qty
        AccountMove = self.env['account.move']
        for cost, qty in quant_cost_qty.items():
            move_lines = self._prepare_account_move_line(move, qty, cost, credit_account_id, debit_account_id)
            date = self.env.context.get('force_period_date', move.date)
            new_move = AccountMove.create({
                'journal_id': journal_id,
                'line_ids': move_lines,
                'date': date,
                'ref': move.picking_id.name})
            new_move.post()
