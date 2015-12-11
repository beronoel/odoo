import openerp.tests

@openerp.tests.common.at_install(False)
@openerp.tests.common.post_install(True)
class TestUi(openerp.tests.HttpCase):
    def test_01_mail_tour(self):
        import pdb; pdb.set_trace()
        self.phantom_js("/", "odoo.__DEBUG__.services['web.Tour'].run('tour_mail', 'test')", "odoo.__DEBUG__.services['web.Tour'].tours.tour_mail", login="admin")
