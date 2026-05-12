# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    reserved_ids = fields.One2many(
        'stock.reserved', 'sale_order_line_id',
        string='Reservations',
        help="Products reserved specifically for this SO line. They become "
             "extra components of the MO auto-created from this line.")
    has_reservations = fields.Boolean(
        compute='_compute_has_reservations', string='Has Reservations')

    def _compute_has_reservations(self):
        for line in self:
            line.has_reservations = bool(line.reserved_ids.filtered(
                lambda r: r.state == 'reserved'))
