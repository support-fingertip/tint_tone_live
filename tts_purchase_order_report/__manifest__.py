# -*- coding: utf-8 -*-
{
    'name': 'TTS Purchase Order Report',
    'version': '19.0.1.0.0',
    'summary': 'Replaces the default Purchase Order PDF report with the TTS layout.',
    'author': 'Tint Tone and Shades',
    'category': 'Purchases',
    'license': 'LGPL-3',
    'depends': ['purchase'],
    'data': [
        'views/purchase_order_views.xml',
        'reports/purchase_order_template.xml',
        'reports/purchase_order_report.xml',
        'reports/invoice_report.xml',
        'reports/invoice_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
