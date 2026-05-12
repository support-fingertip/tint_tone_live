# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Adds Source/Destination location configuration for stock reservations."""
    _inherit = 'res.config.settings'

    source_location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        config_parameter='sales_stock_reservation.source_location_id',
        help="Location from which products will be moved when reserving "
             "stock (e.g. WH/Stock).")
    destination_location_id = fields.Many2one(
        "stock.location",
        string="Destination (Reservation) Location",
        config_parameter='sales_stock_reservation.destination_location_id',
        help="Location where reserved products are stored until the related "
             "Manufacturing Order consumes them.")
