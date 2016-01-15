# -*- coding: utf-8 -*-

from openerp import api, models


class ProjectStage(models.Model):
    _name = "project.task.type"
    _inherit = ['project.task.type']

    @api.multi
    def archive(self, archive, archive_content=True):
        res = super(ProjectStage, self).archive(archive, archive_content=archive_content)
        if archive_content:
            self.env['project.issue'].with_context(active_test=False).search(
                [('stage_id', 'in', self.ids)]).write({'active': not archive})
        return res
