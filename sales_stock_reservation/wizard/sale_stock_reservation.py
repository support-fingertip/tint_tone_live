# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleStockReservation(models.TransientModel):
    """Wizard to manually pick which products to reserve for a sale order
    line. Reserved products are physically moved to the configured
    Reservation Location and saved as stock.reserved records that will be
    appended to the auto-created MO as extra components."""
    _name = "sale.stock.reservation"
    _description = "Sale Stock Reservation Wizard"

    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", required=True, readonly=True)
    line_ids = fields.One2many(
        "sale.stock.reservation.line",
        "wizard_id",
        string="Products to Reserve")
    mail_notification_ids = fields.Many2many(
        "res.users", string="Email Notification")

    def action_reserve_stock(self):
        """Validate, create internal transfer to Reservation Location, then
        save stock.reserved records on the SO line."""
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_("Please add at least one product to reserve."))

        source_id = self.env['ir.config_parameter'].sudo().get_param(
            'sales_stock_reservation.source_location_id')
        destination_id = self.env['ir.config_parameter'].sudo().get_param(
            'sales_stock_reservation.destination_location_id')
        if not source_id or not destination_id:
            raise UserError(_(
                "Please configure the Source and Destination Locations in "
                "Settings → Inventory → Stock Reserve Location."))
        if int(source_id) == int(destination_id):
            raise UserError(_(
                "The Source and Destination Locations must be different."))

        source_location = self.env['stock.location'].browse(int(source_id))
        dest_location = self.env['stock.location'].browse(int(destination_id))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.lot_stock_id', '=', source_location.id),
        ], limit=1)
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search(
                [('code', '=', 'internal')], limit=1)
        if not picking_type:
            raise UserError(_(
                "No internal-transfer picking type was found. Please enable "
                "internal transfers in your warehouse configuration."))

        # Validate every wizard line has a SO line and product
        for line in self.line_ids:
            if not line.sale_order_line_id:
                raise UserError(_(
                    "Please choose the SO line each reserved product "
                    "belongs to."))
            if not line.product_id:
                raise UserError(_("Each row must have a product."))
            if line.reserve_quantity <= 0:
                raise UserError(_(
                    "Reserve quantity must be greater than zero "
                    "(product %s).") % line.product_id.display_name)

        # Build one picking with one move per wizard line
        move_vals_list = []
        for line in self.line_ids:
            move_vals_list.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.reserve_quantity,
                'product_uom': line.product_uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'description_picking': 'Stock Reservation',
                'procure_method': 'make_to_stock',
            }))

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'origin': self.sale_order_id.name,
            'move_ids': move_vals_list,
        })
        picking.action_confirm()
        picking.action_assign()

        # Set quantity done & validate
        for move in picking.move_ids:
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
            else:
                remaining = move.product_uom_qty
                for ml in move.move_line_ids:
                    take = min(ml.quantity, remaining) if ml.quantity \
                        else remaining
                    ml.quantity = take
                    remaining -= take
                    if remaining <= 0:
                        break
        picking.move_ids.picked = True
        result = picking.button_validate()
        if isinstance(result, dict) and result.get('res_model') == \
                'stock.backorder.confirmation':
            wiz = self.env['stock.backorder.confirmation'].browse(
                result.get('res_id'))
            if wiz:
                wiz.with_context(
                    button_validate_picking_ids=picking.ids
                ).process_cancel_backorder()

        # Persist reservation records
        moves = list(picking.move_ids)
        reserved_records = []
        for line, move in zip(self.line_ids, moves):
            reserved_records.append(self.env['stock.reserved'].create({
                'sale_order_id': self.sale_order_id.id,
                'sale_order_line_id': line.sale_order_line_id.id,
                'product_id': line.product_id.id,
                'reserved_quantity': line.reserve_quantity,
                'state': 'reserved',
                'move_id': move.id,
            }))

        self.sale_order_id.state_reservation = 'reserved'

        # Optional notifications
        if self.mail_notification_ids and reserved_records:
            for user in self.mail_notification_ids:
                body = _(
                    "Stock has been reserved on Sale Order %s."
                ) % self.sale_order_id.name
                self.env['mail.mail'].create([{
                    'subject': _("Stock Reservation: %s") %
                               self.sale_order_id.name,
                    'body_html': "<p>%s</p>" % body,
                    'email_to': user.login,
                }]).send()

        return {'type': 'ir.actions.act_window_close'}


class SaleStockReservationLine(models.TransientModel):
    _name = "sale.stock.reservation.line"
    _description = "Wizard line: product to reserve"

    wizard_id = fields.Many2one(
        "sale.stock.reservation", string="Wizard",
        ondelete='cascade', required=True)
    sale_order_line_id = fields.Many2one(
        "sale.order.line", string="For SO Line", required=True,
        domain="[('order_id', '=', parent.sale_order_id)]",
        help="The SO line whose auto-created MO should consume this product.")
    product_id = fields.Many2one(
        "product.product", string="Product", required=True)
    product_uom_id = fields.Many2one(
        "uom.uom", string="UoM", required=True,
        compute='_compute_uom', store=True, readonly=False)
    reserve_quantity = fields.Float(
        string="Reserve Qty", default=1.0, required=True)

    @api.depends('product_id')
    def _compute_uom(self):
        for rec in self:
            if rec.product_id and not rec.product_uom_id:
                rec.product_uom_id = rec.product_id.uom_id
