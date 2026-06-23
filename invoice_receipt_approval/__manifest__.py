# -*- coding: utf-8 -*-
{
    'name': 'Invoice & Receipt Approval',
    'summary': 'Associates submit invoices/receipts for approval before posting when amount exceeds the configured threshold.',
    'description': '',
    'author': 'Tint & Tone',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'version': '19.0.1.0.0',
    'depends': ['base', 'account', 'hr_expense', 'mail'],
    'data': [
        'security/invoice_receipt_approval_groups.xml',
        'security/invoice_report_approval_rules.xml',
        'security/ir.model.access.csv',
        'data/payment_email_template.xml',
        'views/invoice_reject_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/purchase_quotation_templates.xml',
        'views/account_move_views.xml',
        'views/hr_expense_views.xml',
    ],
    'installable': True,
    'application': False,
}
