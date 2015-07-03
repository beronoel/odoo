#!/usr/bin/env python

import xmlrpclib
import csv
import sys
import urllib2
import difflib
import time

class bcolors:
    HEADER = '\033[1m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

class TaxOutputter:
    def __init__(self, runbot_instance_name, output_prefix):
        self.url = 'http://localhost:8069'
        urllib2.urlopen(self.url)

        self.url = self.url + '/xmlrpc'
        self.sock = xmlrpclib.ServerProxy(self.url + '/object')
        self.sock2 = xmlrpclib.ServerProxy(self.url + '/db')
        self.sock3 = xmlrpclib.ServerProxy(self.url + '/common')
        self.sock4 = xmlrpclib.ServerProxy(self.url + '/wizard')
        self.dbname = runbot_instance_name
        self.output_prefix = output_prefix
        self.passwd = 'admin'
        self.uid = self.sock3.login(self.dbname, 'admin', self.passwd)

        # Get groups that grants access right we'll need
        group_system = self.execute('ir.model.data', 'xmlid_to_res_id', 'base.group_system')
        group_user = self.execute('ir.model.data', 'xmlid_to_res_id', 'base.group_user')
        group_multi_currency = self.execute('ir.model.data', 'xmlid_to_res_id', 'base.group_multi_currency')
        group_account_invoice = self.execute('ir.model.data', 'xmlid_to_res_id', 'account.group_account_invoice')
        group_account_user = self.execute('ir.model.data', 'xmlid_to_res_id', 'account.group_account_user')
        group_account_manager = self.execute('ir.model.data', 'xmlid_to_res_id', 'account.group_account_manager')
        self.user_groups = [(4, group_system), (4, group_user), (4, group_multi_currency), (4, group_account_invoice), (4, group_account_user), (4, group_account_manager)]

        # Add multicompany group to admin
        group_erp_manager = self.execute('ir.model.data', 'xmlid_to_res_id', 'base.group_erp_manager')
        group_multi_company = self.execute('ir.model.data', 'xmlid_to_res_id', 'base.group_multi_company')
        admin_groups = self.user_groups + [(4, group_erp_manager), (4, group_multi_company)]
        self.execute('res.users', 'write', [1], {'groups_id': admin_groups})

        # Remove company FK of items we'll use
        all_partners_ids = self.execute('res.partner', 'search', [('name', '!=', False)])
        self.execute('res.partner', 'write', all_partners_ids, {'company_id': False})

    def execute(self, *args):
        return self.sock.execute(self.dbname, self.uid, self.passwd, *args)

    def exec_workflow(self, *args):
        return self.sock.exec_workflow(self.dbname, self.uid, self.passwd, *args)

    def setUpChart(self, chart_template):
        self.chart_template = chart_template

        # create new company, new user in this company with financial manager rights
        self.uid = self.sock3.login(self.dbname, 'admin', 'admin')
        name = 'Test9 asdfaasdf9995' + chart_template['name']
        self.company_id = self.execute('res.company', 'search', [('name', '=', name)])
        if self.company_id:
            self.company_id = self.company_id[0]
        else:
            self.company_id = self.execute('res.company', 'create', {'name': name, 'currency_id': 1, 'rml_header': 'lol', 'rml_header2': 'lol', 'rml_header3': 'lol', 'rml_header1': False})
        userid = self.execute('res.users', 'search', [('name', '=', name)])
        if userid:
            userid = userid[0]
        else:
            userid = self.execute('res.users', 'create', {'name': name, 'login': name, 'password': self.passwd, 'email': 'kikoo@lol.com', 'company_id': self.company_id, 'company_ids': [[6, False, [self.company_id]]], 'active': True})
        self.execute('res.users', 'write', [userid], {'groups_id': self.user_groups})

        # Login as new user
        self.uid = self.sock3.login(self.dbname, name, self.passwd)

        # Set chart of accounts
        sale_tax_ids = False
        purchase_tax_ids = False
        if chart_template['complete_tax_set']:
            sale_tax_ids = self.execute('account.tax.template', 'search', [("chart_template_id", "=", chart_template['id']), ('type_tax_use', 'in', ('sale','all'))], 0, 1, "sequence, id desc")
            purchase_tax_ids = self.execute('account.tax.template', 'search', [("chart_template_id", "=", chart_template['id']), ('type_tax_use', 'in', ('purchase','all'))], 0, 1, "sequence, id desc")
        wizard_id = self.execute('wizard.multi.charts.accounts', 'create', {
                'company_id': self.company_id,
                'chart_template_id': chart_template['id'],
                'code_digits': chart_template['code_digits'] or 6,
                'bank_account_code_char': chart_template['bank_account_code_char'] or 'BNK',
                'sale_tax': sale_tax_ids and sale_tax_ids[0] or False,
                'purchase_tax': purchase_tax_ids and purchase_tax_ids[0] or False,
                'sale_tax_rate': 15,
                'purchase_tax_rate': 15,
                'complete_tax_set': chart_template['complete_tax_set'],
                'currency_id': 1,
                'transfer_account_id': chart_template['transfer_account_id'][0]
            })
        self.execute('wizard.multi.charts.accounts', 'execute', [wizard_id])

    def check_taxes(self, op_type):
        print '\n' + bcolors.HEADER + 'START : ' + self.chart_template['name'] + ' - ' + op_type + ' - ' + self.output_prefix + bcolors.ENDC
        if op_type == 'sale':
            journal_id = self.execute('account.journal', 'search', [('type', '=', 'sale'), ('company_id', '=', self.company_id)])[0]
            ref_journal_id = self.execute('account.journal', 'search', [('type', '=', 'sale'), ('company_id', '=', self.company_id)])[0]
            partner_id = self.execute('res.partner', 'search', [('name', '=', 'Agrolait')])[0]
            account_id = self.execute('account.account', 'search', [('user_type.type', '=', 'receivable')])[0]
            inv_type = 'out_invoice'
            refund_type = 'out_refund'
            csv_file = self.output_prefix + '-' + self.chart_template['name'] + '-sale.csv'
            tax_types = ['sale', 'all']
        elif op_type == 'purchase':
            journal_id = self.execute('account.journal', 'search', [('type', '=', 'purchase'), ('company_id', '=', self.company_id)])[0]
            ref_journal_id = self.execute('account.journal', 'search', [('type', '=', 'purchase'), ('company_id', '=', self.company_id)])[0]
            partner_id = self.execute('res.partner', 'search', [('name', '=', 'China Export')])[0]
            account_id = self.execute('account.account', 'search', [('user_type.type', '=', 'payable')])[0]
            inv_type = 'in_invoice'
            refund_type = 'in_refund'
            csv_file = self.output_prefix + '-' + self.chart_template['name'] + '-purchase_ordered.csv'
            tax_types = ['purchase', 'all']

        #get_financial_report references
        tax_grid_ids = self.execute('account.financial.report.line', 'search', [('code', 'like', 'BETAX%')])
        tax_grids = self.execute('account.financial.report.line', 'read', tax_grid_ids, ['domain', 'code', 'formulas'])

        master_invoice_id = self.execute('account.invoice', 'create', {'partner_id': partner_id, 'type': inv_type, 'journal_id': journal_id, 'account_id': account_id})
        self.execute('account.invoice.line', 'create', {'name': 'toto', 'invoice_id': master_invoice_id, 'price_unit': 1000}, {'journal_id': journal_id})
        master_refund_id = self.execute('account.invoice', 'create', {'partner_id': partner_id, 'type': refund_type, 'journal_id': ref_journal_id, 'account_id': account_id})
        self.execute('account.invoice.line', 'create', {'name': 'toto', 'invoice_id': master_refund_id, 'price_unit': 1000}, {'journal_id': journal_id})
        #prepare the csv file to store the accounting entries to compare
        with open(csv_file, 'wb') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['tax code', 'TYPE (invoice/refund)', 'account_id', 'debit', 'credit', 'invoice amount untaxed', 'invoice amount tax', 'invoice total', 'vat declaration', 'tax amount'])
            #search all the taxes
            tax_ids = self.execute('account.tax', 'search', [('type_tax_use', 'in', tax_types), ('name', 'not like', '-C2'), ('name', 'not like', '-C3')])
            #tax_ids = self.execute('account.tax', 'search', [('type_tax_use', 'in', tax_types), ('description', 'in', ['VAT-IN-V82-CAR-EXC','VAT-IN-V83-06-CC'])])
            #tmp = 0
            for tax_id in tax_ids:
                #if tmp > 3:
                #    continue
                #tmp += 1
                tax_code = self.execute('account.tax', 'read', [tax_id], ['description'])[0]['description']
                print 'tax:', tax_code
                #add this tax in the global invoice
                # self.execute('account.invoice.line', 'write', [master_inv_line_id], {'invoice_line_tax_id': [(4, tax_id)]})
                # self.execute('account.invoice.line', 'write', [master_ref_line_id], {'invoice_line_tax_id': [(4, tax_id)]})
                #make an invoice with this tax
                tmp_invoice_id = self.execute('account.invoice', 'create', {'partner_id': partner_id, 'type': inv_type, 'journal_id': journal_id, 'account_id': account_id})
                self.execute('account.invoice.line', 'create', {'name': 'toto', 'invoice_id': tmp_invoice_id, 'price_unit': 1000, 'invoice_line_tax_ids': [(6, 0, [tax_id])]}, {'journal_id': journal_id})
                tmp_refund_id = self.execute('account.invoice', 'create', {'partner_id': partner_id, 'type': refund_type, 'journal_id': ref_journal_id, 'account_id': account_id})
                self.execute('account.invoice.line', 'create', {'name': 'toto', 'invoice_id': tmp_refund_id, 'price_unit': 1000, 'invoice_line_tax_ids': [(6, 0, [tax_id])]}, {'journal_id': journal_id})
                #validate the invoice and the refund
                #self.execute('account.invoice', 'signal_workflow', [tmp_invoice_id, tmp_refund_id], 'invoice_open')
                self.execute('account.invoice', 'compute_taxes', tmp_invoice_id)
                self.exec_workflow('account.invoice', 'invoice_open', tmp_invoice_id)
                time.sleep(2) # Sometimes causes concurrent update
                self.execute('account.invoice', 'compute_taxes', tmp_refund_id)
                self.exec_workflow('account.invoice', 'invoice_open', tmp_refund_id)
                #write down the accounting entries in a csv file
                writer.writerow([])
                writer.writerow([tax_code, tax_code, tax_code, tax_code, tax_code, tax_code, tax_code, tax_code, tax_code])
                for obj_id in [tmp_invoice_id, tmp_refund_id]:
                #for obj_id in [tmp_refund_id]:
                    writer.writerow([])
                    invoice_data = self.execute('account.invoice', 'read', [obj_id], ['id', 'amount_untaxed', 'amount_tax', 'amount_total', 'type', 'move_id'])[0]
                    aml_ids = self.execute('account.move.line', 'search', [('move_id', '=', invoice_data['move_id'][0])])
                    l = self.execute('account.move.line', 'read', aml_ids, ['id', 'name', 'account_id', 'debit', 'credit', 'tax_ids', 'tax_line_id'])
                    for aml_data in sorted(l, key=lambda row: (row['debit'],row['credit'])):
                        #aml_data.values() + invoice_data.values()
                        tax_codes = []
                        for vat_grid in tax_grids:
                            sign = 1
                            if vat_grid['domain']:
                                dom = eval(vat_grid['domain'])
                                applicability = self.execute('account.move.line', 'search', dom + [('id', '=', aml_data['id'])])
                                if applicability:
                                    if vat_grid['formulas'] == "balance = sum.credit":
                                        sign = -1
                                    positive = aml_data['debit'] > 0 and 1 or -1
                                    sign = positive*sign > 0 and '+' or '-'
                                    tax_codes.append(sign+vat_grid['code'])
                        vals = [tax_code, invoice_data['type'], aml_data['account_id'][1].split(' ')[0], aml_data['debit'], aml_data['credit'], invoice_data['amount_untaxed'], invoice_data['amount_tax'], invoice_data['amount_total'], str(tax_codes), tax_codes and abs(aml_data['debit'] - aml_data['credit']) or 0.0]
                        writer.writerow([unicode(s).encode('utf-8') for s in vals])
                        #print op_type, 'added row in csv'
            ##validate the master invoice and refund
            #self.exec_workflow('account.invoice', 'invoice_open', master_invoice_id)
            #self.exec_workflow('account.invoice', 'invoice_open', master_refund_id)
            ##write down the accounting entries in a csv file
            #print 'write master rows'
            #for obj_id in [master_invoice_id, master_refund_id]:
            #    invoice_data = self.execute('account.invoice', 'read', [obj_id], ['amount_untaxed', 'amount_tax', 'amount_total', 'type', 'move_id'])[0]
            #    aml_ids = self.execute('account.move.line', 'search', [('move_id', '=', invoice_data['move_id'][0])])
            #    l = self.execute('account.move.line', 'read', aml_ids, ['id', 'name', 'account_id', 'debit', 'credit'])
            #    for aml_data in sorted(l, key=lambda row: (row['debit'],row['credit'])):
            #        vals = ['master', invoice_data['type'], aml_data['name'], aml_data['account_id'][1], aml_data['debit'], aml_data['credit'], invoice_data['amount_untaxed'], invoice_data['amount_tax'], invoice_data['amount_total']]
            #        writer.writerow([unicode(s).encode('utf-8') for s in vals])
            #return csv_file

    def print_chart(self):
        tax_code_ids = self.execute('account.tax.code', 'search', [('child_ids', '=', False), ('company_id', '=', self.company_id)])
        csv_file = self.output_prefix + '-' + self.chart_template['name'] + '-chart of taxes.csv'
        with open(csv_file, 'wb') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['tax case name', 'code', 'period sum'])
            for tax_code_id in tax_code_ids:
                tax_code = self.execute('account.tax.code', 'read', [tax_code_id], ['name', 'code', 'sum'])[0]
                vals = [tax_code['name'], tax_code['code'], tax_code['sum']]
                writer.writerow([unicode(s).encode('utf-8') for s in vals])
        return


def logResult(chart_templates, op_type, file1):
    output_a = open(file1, 'r').read()
    # output_b = open(file2, 'r').read()
    print '\n'
    if output_a != output_b:
        log_file_name = chart_templates['name'] + '-' + op_type + '-debug'
        log_file = open('./'+log_file_name, 'w+')
        print bcolors.FAIL + 'FAIL : ' + chart_templates['name'] + ' - ' + op_type + '\n' + 'Details in file ' + log_file_name + bcolors.ENDC
        for line in difflib.unified_diff(output_a.strip().splitlines(), output_b.strip().splitlines(), fromfile=file1, tofile=file2, lineterm=''):
            log_file.write(line+'\n')
    else:
        print bcolors.OKGREEN + 'OK : ' + chart_templates['name'] + ' - sale' + bcolors.ENDC


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'Usage : %s runbot_instance_v8_name [account_chart_template_id+?]' % sys.argv[0]
        sys.exit()

    chart_templates_domain = [('visible', '=', True)]
    if len(sys.argv) == 3:
        if sys.argv[2].endswith('+'):
            chart_templates_domain += [('id', '>=', sys.argv[2][:-1])]
        else:
            chart_templates_domain += [('id', '=', sys.argv[2])]

    v8_outputter = TaxOutputter(sys.argv[1], 'v9')
    # new_design_outputter = TaxOutputter(sys.argv[2], 'new_design')

    chart_templates_ids = v8_outputter.execute('account.chart.template', 'search', chart_templates_domain, 0, 9999, "id desc")
    chart_templates = v8_outputter.execute('account.chart.template', 'read', chart_templates_ids, ['id', 'name', 'complete_tax_set', 'code_digits', 'bank_account_code_char', 'transfer_account_id'])

    for chart_template in chart_templates:
        v8_outputter.setUpChart(chart_template)
        # new_design_outputter.setUpChart(chart_template)
        v8_outputter.check_taxes('sale')
        v8_outputter.check_taxes('purchase')
