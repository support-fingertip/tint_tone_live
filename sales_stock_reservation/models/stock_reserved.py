# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class StockReserved(models.Model):
    """
    Stores reserved products per Sale Order Line.

    Each record represents ONE reserved product earmarked for ONE specific
    sale order line. When the SO is confirmed and an MO is auto-created for
    that line, these reserved products are appended as extra components to
    the MO (sourced from the Stock Reservation Location).
    """
    _name = "stock.reserved"
    _description = "Reserved stock for Sale Order"

    name = fields.Char(string="Reference", readonly=True, copy=False,
                       default=lambda self: _('New'))
    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order",
        ondelete='cascade', readonly=True)
    sale_order_line_id = fields.Many2one(
        "sale.order.line", string="For SO Line",
        ondelete='cascade',
        help="The specific sale order line this reservation belongs to. "
             "Reserved products are added as extra components to the MO "
             "auto-created from this line.")
    product_id = fields.Many2one(
        "product.product", string="Reserved Product", required=True)
    product_uom_id = fields.Many2one(
        "uom.uom", string="UoM",
        related='product_id.uom_id', readonly=True)
    reserved_quantity = fields.Float(string="Reserved Qty", required=True)
    move_id = fields.Many2one(
        "stock.move", string="Reserve Move",
        readonly=True,
        help="The internal-transfer move that physically placed the product "
             "in the Reservation Location.")
    consumed_in_mo_id = fields.Many2one(
        "mrp.production", string="Consumed in MO", readonly=True,
        help="The manufacturing order whose components include this "
             "reserved product.")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('reserved', 'Reserved'),
        ('consumed', 'Consumed by MO'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'stock.reserved') or _('New')
        return super().create(vals_list)

    def _return_reserved_stock(self):
        """Move the reserved product back from Reservation Location to the
        original source location. Used when cancelling a reservation."""
        for rec in self:
            if rec.state != 'reserved':
                continue
            source_id = self.env['ir.config_parameter'].sudo().get_param(
                'sales_stock_reservation.source_location_id')
            destination_id = self.env['ir.config_parameter'].sudo().get_param(
                'sales_stock_reservation.destination_location_id')
            if not source_id or not destination_id:
                continue

            picking_type = self.env['stock.picking.type'].search(
                [('code', '=', 'internal')], limit=1)
            if not picking_type:
                continue

            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': int(destination_id),
                'location_dest_id': int(source_id),
                'origin': 'Cancel reservation %s' % rec.name,
                'move_ids': [(0, 0, {
                    'product_id': rec.product_id.id,
                    'product_uom_qty': rec.reserved_quantity,
                    'product_uom': rec.product_uom_id.id,
                    'location_id': int(destination_id),
                    'location_dest_id': int(source_id),
                    'description_picking': 'Cancel Stock Reservation',
                    'procure_method': 'make_to_stock',
                })],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                for ml in move.move_line_ids:
                    ml.quantity = move.product_uom_qty
                if not move.move_line_ids:
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': move.product_uom_qty,
                        'picking_id': picking.id,
                    })
            picking.move_ids.picked = True
            picking.button_validate()
            rec.state = 'cancel'

    def _safe_link_move_to_reservation(self, move):
        """Store the consuming MO's raw-material move on the reservation
        record (best-effort; we only update if the field is empty)."""
        for rec in self:
            if not rec.move_id:
                rec.move_id = move.id
