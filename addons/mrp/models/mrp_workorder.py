# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class MrpProductionWorkcenterLine(models.Model):
    _name = 'mrp.workorder'
    _description = 'Work Order'
    _inherit = ['mail.thread']

    name = fields.Char(
        'Work Order', required=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    workcenter_id = fields.Many2one(
        'mrp.workcenter', 'Work Center', required=True,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    duration = fields.Float(
        'Expected Duration', digits=(16, 2),
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},
        help="Expected duration in minutes")
    production_id = fields.Many2one(
        'mrp.production', 'Manufacturing Order',
        index=True, ondelete='cascade', required=True, track_visibility='onchange',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    state = fields.Selection([
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('progress', 'In Progress'),
        ('done', 'Finished'),
        ('cancel', 'Cancelled')], string='Status',
        default='pending')
    date_planned_start = fields.Datetime(
        'Scheduled Date Start',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    date_planned_end = fields.Datetime(
        'Scheduled Date Finished',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    date_start = fields.Datetime(
        'Effective Start Date',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    date_finished = fields.Datetime(
        'Effective End Date',
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    delay = fields.Float(
        'Real Duration', compute='_compute_delay',
        readonly=True, store=True)
    delay_unit = fields.Float(
        'Duration Per Unit', compute='_compute_delay',
        readonly=True, store=True)
    delay_percent = fields.Integer(
        'Duration Deviation (%)', compute='_compute_delay',
        group_operator="avg", readonly=True, store=True)
    qty_produced = fields.Float(
        'Quantity', default=0.0,
        readonly=True,
        help="The number of products already handled by this work order")  # TODO: decimal precision
    operation_id = fields.Many2one(
        'mrp.routing.workcenter', 'Operation')  # Should be used differently as BoM can change in the meantime
    move_raw_ids = fields.One2many(
        'stock.move', 'workorder_id', 'Moves')
    move_lot_ids = fields.One2many(
        'stock.move.lots', 'workorder_id', 'Moves to Track',
        domain=[('done_wo', '=', True)],
        help="Inventory moves for which you must scan a lot number at this work order")
    active_move_lot_ids = fields.One2many(
        'stock.move.lots', 'workorder_id',
        domain=[('done_wo', '=', False)])
    availability = fields.Selection(
        'Stock Availability',
        related='production_id.availability', store=True)
    production_state = fields.Selection(
        'Production State',
        related='production_id.state', readonly=True)  # TDE FIXME: not store ?
    product = fields.Many2one(
        'product.product', 'Product',
        readonly=True, related='production_id.product_id')  # should be product_id
    has_tracking = fields.Selection(related='production_id.product_id.tracking')
    qty = fields.Float('Qty', readonly=True, related='production_id.product_qty')
    uom = fields.Many2one('product.uom', related='production_id.product_uom_id', string='Unit of Measure')  # TDE FIXME: learn how to name fields

    time_ids = fields.One2many(
        'mrp.workcenter.productivity', 'workorder_id')  # TDE FIXME: renaming ?
    worksheet = fields.Binary(
        'Worksheet', related='operation_id.worksheet', readonly=True)
    show_state = fields.Boolean(compute='_get_current_state')
    production_messages = fields.Html(compute="_compute_production_messages")
    final_lot_id = fields.Many2one('stock.production.lot', 'Current Lot', domain="[('product_id', '=', product)]")
    qty_producing = fields.Float('Qty Producing', default=1.0, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    next_work_order_id = fields.Many2one('mrp.workorder', "Next Work Order")
    tracking = fields.Selection(related='product.tracking', readonly=True)
    is_produced = fields.Boolean(compute='_is_produced')
    working_state = fields.Selection(related='workcenter_id.working_state')

    @api.multi
    @api.depends('time_ids.date_end')
    def _compute_delay(self):
        for workorder in self:
            duration = sum(workorder.time_ids.mapped('duration'))
            workorder.delay = duration
            workorder.delay_unit = round(duration / max(workorder.qty_produced, 1), 2)
            if duration:
                workorder.delay_percent = 100 * (workorder.duration - duration) / duration
            else:
                workorder.delay_percent = 0

    def _get_current_state(self):
        for order in self:
            if order.time_ids.filtered(lambda x : (x.user_id.id == self.env.user.id) and (not x.date_end) and (x.loss_type in ('productive', 'performance'))):
                order.show_state = True
            else:
                order.show_state = False

    @api.depends('production_id', 'workcenter_id', 'production_id.bom_id')
    def _compute_production_messages(self):
        ProductionMessage = self.env['mrp.message']
        for workorder in self:
            domain = ['|', ('bom_id', '=', workorder.production_id.bom_id.id), '|',
                ('workcenter_id', '=', workorder.workcenter_id.id),
                ('routing_id', '=', workorder.operation_id.routing_id.id),
                ('valid_until', '>=', fields.Date.today())
            ]
            messages = ProductionMessage.search(domain).mapped('message')
            workorder.production_messages = "<br/>".join(messages) or False  # TDE FIXME: or False ? not necessary I think

    @api.depends('qty', 'qty_produced')
    def _is_produced(self):
        for workorder in self:
            if workorder.qty_produced >= workorder.qty:
                workorder.is_produced = True

    @api.onchange('qty_producing')
    def _onchange_qty_producing(self):
        moves = self.move_raw_ids.filtered(lambda x: (x.state not in ('done', 'cancel')) and (x.product_id.tracking != 'none') and (x.product_id.id != self.product.id))
        for move in moves:
            existing_move_lots = self.active_move_lot_ids.filtered(lambda x: (x.move_id.id == move.id))
            qty = self.qty_producing / move.bom_line_id.bom_id.product_qty * move.bom_line_id.product_qty
            if move.product_id.tracking == 'lot':
                if existing_move_lots:
                    existing_move_lots[0].quantity = qty
            elif move.product_id.tracking == 'serial':
                if existing_move_lots:
                    #Create extra pseudo record
                    sum_quantities = sum([x.quantity for x in existing_move_lots])
                    if sum_quantities < qty:
                        qty_todo = qty - sum_quantities
                        while qty_todo > 0:
                            self.active_move_lot_ids += self.env['stock.move.lots'].new({'move_id': move.id,
                                                                                        'product_id': move.product_id.id,
                                                                                        'lot_id': False,
                                                                                        'quantity': min(1.0, qty_todo),
                                                                                        'quantity_done': 0,
                                                                                        'workorder_id': self.id,
                                                                                        'done_wo': False})
                            qty_todo -= 1
                    elif qty < sum_quantities:
                        qty_todo = sum_quantities - qty
                        for movelot in existing_move_lots:
                            if qty_todo <= 0:
                                break
                            if (movelot.quantity_done == 0) and (qty_todo - movelot.quantity > 0):
                                qty_todo -= movelot.quantity
                                self.active_move_lot_ids -= movelot
                            else:
                                movelot.quantity = movelot.quantity - qty_todo
                                qty_todo = 0

    @api.multi
    def write(self, values):
        if any([x.state == 'done' for x in self]) and values.get('date_planned_start') and values.get('date_planned_end'):
            raise UserError(_('You can not change the finished work order.'))
        return super(MrpProductionWorkcenterLine, self).write(values)

    def _generate_lot_ids(self):
        """
            Generate stock move lots
        """
        self.ensure_one()
        move_lot_obj = self.env['stock.move.lots']
        if self.move_raw_ids:
            moves = self.move_raw_ids.filtered(lambda x: (x.state not in ('done', 'cancel')) and (x.product_id.tracking != 'none') and (x.product_id.id != self.product.id))
            for move in moves:
                qty = self.qty_producing / move.bom_line_id.bom_id.product_qty * move.bom_line_id.product_qty
                if move.product_id.tracking=='serial':
                    while float_compare(qty, 0.0, precision_rounding=move.product_uom.rounding) > 0:
                        move_lot_obj.create({
                            'move_id': move.id,
                            'quantity': min(1,qty),
                            'quantity_done': 0,
                            'production_id': self.production_id.id,
                            'workorder_id': self.id,
                            'product_id': move.product_id.id,
                            'done_wo': False,
                        })
                        qty -= 1
                else:
                    move_lot_obj.create({
                        'move_id': move.id,
                        'quantity': qty,
                        'quantity_done': 0,
                        'product_id': move.product_id.id,
                        'production_id': self.production_id.id,
                        'workorder_id': self.id,
                        'done_wo': False,
                        })

    @api.multi
    def record_production(self):
        self.ensure_one()
        if self.qty_producing <= 0:
            raise UserError(_('Please set the quantity you produced in the Current Qty field. It can not be 0!'))

        if (self.production_id.product_id.tracking != 'none') and not self.final_lot_id:
            raise UserError(_('You should provide a lot for the final product'))

        # Update quantities done on each raw material line
        raw_moves = self.move_raw_ids.filtered(lambda x: (x.has_tracking == 'none') and (x.state not in ('done', 'cancel')) and x.bom_line_id)
        for move in raw_moves:
            if move.unit_factor:
                move.quantity_done += self.qty_producing * move.unit_factor

        # Transfer quantities from temporary to final move lots or make them final
        for move_lot in self.active_move_lot_ids:
            #Check if move_lot already exists
            if move_lot.quantity_done <= 0: #rounding...
                move_lot.unlink()
                continue
            if not move_lot.lot_id:
                raise UserError(_('You should provide a lot for a component'))
            #Search other move_lot where it could be added:
            lots = self.move_lot_ids.filtered(lambda x: (x.lot_id.id == move_lot.lot_id.id) and (not x.lot_produced_id) and (not x.done_move))
            if lots:
                lots[0].quantity_done += move_lot.quantity_done
                lots[0].lot_produced_id = self.final_lot_id.id
                move_lot.unlink()
            else:
                move_lot.lot_produced_id = self.final_lot_id.id
                move_lot.done_wo = True

        # One a piece is produced, you can launch the next work order
        if self.next_work_order_id.state=='pending':
            self.next_work_order_id.state='ready'
        if self.next_work_order_id and self.final_lot_id and not self.next_work_order_id.final_lot_id:
            self.next_work_order_id.final_lot_id = self.final_lot_id.id

        #TODO: add filter for those that have not been done yet --> need to check as it can have different filters
        self.move_lot_ids.filtered(lambda x: not x.done_move and not x.lot_produced_id).write({'lot_produced_id': self.final_lot_id.id,
                                          'lot_produced_qty': self.qty_producing,})

        # If last work order, then post lots used
        #TODO: should be same as checking if for every workorder something has been done?
        if not self.next_work_order_id:
            production_move = self.production_id.move_finished_ids.filtered(lambda x: (x.product_id.id == self.production_id.product_id.id) and (x.state not in ('done', 'cancel')))
            if production_move.product_id.tracking != 'none':
                move_lot = production_move.move_lot_ids.filtered(lambda x: x.lot_id.id == self.final_lot_id.id)
                if move_lot:
                    move_lot.quantity += self.qty_producing
                else:
                    move_lot.create({'move_id': production_move.id,
                                     'lot_id': self.final_lot_id.id,
                                     'quantity': self.qty_producing,
                                     'quantity_done': self.qty_producing,
                                     'workorder_id': self.id,
                                     })
            else:
                production_move.quantity_done += self.qty_producing #TODO: UoM conversion?
        # Update workorder quantity produced
        self.qty_produced += self.qty_producing

        # Set a qty producing 
        if self.qty_produced >= self.qty:
            self.qty_producing = 0
        elif self.product.tracking == 'serial':
            self.qty_producing = 1.0
            self._generate_lot_ids()
        else:
            self.qty_producing = self.qty - self.qty_produced
            self._generate_lot_ids()

        self.final_lot_id = False
        if self.qty_produced >= self.qty:
            self.button_finish()

    @api.multi
    def button_start(self):
        timeline = self.env['mrp.workcenter.productivity']
        if self.delay < self.duration:
            loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type','=','productive')], limit=1)
            if not len(loss_id):
                raise UserError(_("You need to define at least one productivity loss in the category 'Productivity'. Create one from the Manufacturing app, menu: Configuration / Productivity Losses."))
        else:
            loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type','=','performance')], limit=1)
            if not len(loss_id):
                raise UserError(_("You need to define at least one productivity loss in the category 'Performance'. Create one from the Manufacturing app, menu: Configuration / Productivity Losses."))
        for workorder in self:
            if workorder.production_id.state != 'progress':
                workorder.production_id.state = 'progress'
            timeline.create({
                'workorder_id': workorder.id,
                'workcenter_id': workorder.workcenter_id.id,
                'description': _('Time Tracking: ')+self.env.user.name,
                'loss_id': loss_id[0].id,
                'date_start': datetime.now(),
                'user_id': self.env.user.id
            })
        self.write({'state': 'progress',
                    'date_start': datetime.now(),
        })

    @api.multi
    def button_finish(self):
        self.ensure_one()
        self.end_all()
        self.write({'state': 'done', 'date_finished': fields.Datetime.now()})
        if not self.production_id.workorder_ids.filtered(lambda x: x.state not in ('done','cancel')):
            self.production_id.post_inventory() # User should put it to done manually

    @api.multi
    def end_previous(self, doall=False):
        timeline_obj = self.env['mrp.workcenter.productivity']
        domain = [('workorder_id', 'in', self.ids), ('date_end', '=', False)]
        if not doall:
            domain.append(('user_id', '=', self.env.user.id))
        for timeline in timeline_obj.search(domain, limit=doall and None or 1):
            wo = timeline.workorder_id
            if timeline.loss_type <> 'productive':
                timeline.write({'date_end': fields.Datetime.now()})
            else:
                maxdate = fields.Datetime.from_string(timeline.date_start) + relativedelta(minutes=wo.duration - wo.delay)
                enddate = datetime.now()
                if maxdate > enddate:
                    timeline.write({'date_end': enddate})
                else:
                    timeline.write({'date_end': maxdate})
                    loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type','=','performance')], limit=1)
                    if not len(loss_id):
                        raise UserError(_("You need to define at least one unactive productivity loss in the category 'Performance'. Create one from the Manufacturing app, menu: Configuration / Productivity Losses."))
                    timeline.copy({'date_start': maxdate, 'date_end': enddate, 'loss_id': loss_id.id})

    @api.multi
    def end_all(self):
        return self.end_previous(doall=True)

    @api.multi
    def button_pending(self):
        self.end_previous()

    @api.multi
    def button_unblock(self):
        for order in self:
            order.workcenter_id.unblock()

    @api.multi
    def action_cancel(self):
        self.write({'state': 'cancel'})

    @api.multi
    def button_done(self):
        if any([x.state in ('done', 'cancel') for x in self]):
            raise UserError(_('A Manufacturing Order is already done or cancelled!'))
        self.end_all()
        self.write({'state': 'done',
                    'date_finished': datetime.now()})

    @api.multi
    def button_scrap(self):
        self.ensure_one()
        return {
            'name': _('Scrap'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.scrap',
            'view_id': self.env.ref('stock.stock_scrap_form_view2').id,
            'type': 'ir.actions.act_window',
            'context': {'product_ids': self.production_id.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')).mapped('product_id').ids + [self.product.id]},
            'target': 'new',
        }
