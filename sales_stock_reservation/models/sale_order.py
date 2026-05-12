# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    apply_stock_reservation = fields.Boolean(
        string="Apply Stock Reservation",
        help="Tick to enable per-line stock reservation. The reserved "
             "products will become extra components on the auto-created MO.")
    state_reservation = fields.Selection([
        ('reserved', 'Reserved'),
        ('cancel', 'Cancelled'),
    ], string='Reservation Status', copy=False, readonly=True)
    reserved_ids = fields.One2many(
        'stock.reserved', 'sale_order_id',
        string='Stock Reservations')
    reserved_count = fields.Integer(
        compute='_compute_reserved_count', string='Reserved Count')

    def _compute_reserved_count(self):
        for order in self:
            order.reserved_count = len(order.reserved_ids.filtered(
                lambda r: r.state == 'reserved'))

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------
    def action_create_stock_reservation(self):
        """Open the wizard for selecting products to reserve."""
        self.ensure_one()
        return {
            'name': _("Create Stock Reservation"),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.stock.reservation',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'sales_stock_reservation.sale_stock_reservation_view_form').id,
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def action_cancel_reservation(self):
        """Move reserved products back from Reservation Location to source."""
        for order in self:
            for reserved in order.reserved_ids.filtered(
                    lambda r: r.state == 'reserved'):
                reserved._return_reserved_stock()
            order.state_reservation = 'cancel'
        return True

    def action_view_reserved_stock(self):
        self.ensure_one()
        return {
            'name': _('Reserved Stock'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.reserved',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

    # ------------------------------------------------------------------
    # OVERRIDES
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Before confirming the SO, check that every reserved product has
        positive Qty On Hand at WH/Stock. If insufficient stock is found,
        send an email notification (does NOT block the confirmation)."""
        for order in self:
            if not order.apply_stock_reservation:
                continue
            order._check_reserved_products_stock()
        return super().action_confirm()

    def _check_reserved_products_stock(self):
        """For each reserved product on this SO, verify Qty On Hand at the
        configured Source Location (typically WH/Stock) is greater than 0.
        If any product has insufficient stock, send an email notification
        and post a message in the chatter — but do NOT block the SO
        confirmation."""
        self.ensure_one()
        active_reservations = self.reserved_ids.filtered(
            lambda r: r.state == 'reserved')
        if not active_reservations:
            return

        source_id = self.env['ir.config_parameter'].sudo().get_param(
            'sales_stock_reservation.source_location_id')
        if not source_id:
            source_location = False
        else:
            source_location = self.env['stock.location'].browse(
                int(source_id))

        insufficient = []  # list of (product, qty_on_hand, required)
        for reservation in active_reservations:
            product = reservation.product_id
            if hasattr(product, 'is_storable') and not product.is_storable:
                continue
            if source_location:
                on_hand = product.with_context(
                    location=source_location.id
                ).qty_available
            else:
                on_hand = product.with_company(self.company_id).qty_available

            if on_hand <= 0:
                insufficient.append((
                    product, on_hand, reservation.reserved_quantity))

        if not insufficient:
            return

        location_name = (source_location.display_name
                         if source_location else 'WH/Stock')

        # Build HTML body for the email/chatter
        rows_html = "".join([
            "<tr>"
            "<td style='padding:4px 8px;border:1px solid #ddd;'>%s</td>"
            "<td style='padding:4px 8px;border:1px solid #ddd;text-align:right;'>%s</td>"
            "<td style='padding:4px 8px;border:1px solid #ddd;text-align:right;'>%s</td>"
            "</tr>" % (p.display_name, on_hand, required)
            for p, on_hand, required in insufficient
        ])
        body_html = (
                        "<p>Stock alert for Sale Order <strong>%s</strong>:</p>"
                        "<p>The following reserved product(s) do not have sufficient "
                        "stock at <strong>%s</strong>:</p>"
                        "<table style='border-collapse:collapse;'>"
                        "<thead><tr>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Product</th>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Qty On Hand</th>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Required</th>"
                        "</tr></thead>"
                        "<tbody>%s</tbody>"
                        "</table>"
                        "<p>Please replenish the stock or review the reservation.</p>"
                    ) % (self.name, location_name, rows_html)

        subject = _(
            "Stock Alert: Insufficient stock for reserved products on %s"
        ) % self.name

        # Collect recipient emails
        recipient_emails = []
        if self.user_id and self.user_id.partner_id.email:
            recipient_emails.append(self.user_id.partner_id.email)
        if self.partner_id and self.partner_id.email and \
                self.partner_id.email not in recipient_emails:
            recipient_emails.append(self.partner_id.email)

        # Send the email
        if recipient_emails:
            try:
                self.env['mail.mail'].sudo().create({
                    'subject': subject,
                    'body_html': body_html,
                    'email_to': ", ".join(recipient_emails),
                    'auto_delete': True,
                }).send()
            except Exception as e:
                # Don't crash SO confirm if mail fails
                import logging
                logging.getLogger(__name__).warning(
                    "sales_stock_reservation: failed to send stock alert "
                    "mail for SO %s: %s", self.name, e)


        # Also post a message in the chatter so it's visible on the SO
        from markupsafe import Markup
        self.message_post(
            body=Markup(body_html),
            subject=subject,
        )
