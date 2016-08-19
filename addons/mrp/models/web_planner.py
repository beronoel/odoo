# -*- coding: utf-8 -*-

from odoo import models


class PlannerMrp(models.Model):
    _inherit = 'web.planner'

    def _get_planner_application(self):
        planner = super(PlannerMrp, self)._get_planner_application()
        planner.append(['planner_mrp', 'MRP Planner'])
        return planner
