# -*- coding: utf-8 -*-
{
    'name': 'Sales Stock Reservation (MO Components)',
    'version': "19.0.2.0.0",
    'category': 'Sales,Warehouse,Manufacturing',
    'summary': """Reserve products for a sale order; reserved products are
    added as extra components to the auto-created Manufacturing Order without
    affecting the original BoM.""",
    'description': """
This module lets users pre-reserve specific products against a sale order
*before* confirmation. Those reserved products are physically moved to a
configured Stock Reservation Location.

When the sale order is confirmed and a Manufacturing Order is auto-created
(via MTO + Manufacture route), the reserved products are appended to the MO's
raw-material lines (move_raw_ids), with their source location set to the
Stock Reservation Location. The original BoM is NOT modified.
""",
    'author': "Custom",
    'depends': ['base', 'sale_management', 'stock', 'mrp', 'purchase', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_location_data.xml',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/mrp_production_views.xml',
        'wizard/sale_stock_reservation_views.xml',
    ],
    'license': "LGPL-3",
    'installable': True,
    'auto_install': False,
    'application': False,
}
