# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    sale_reserved_ids = fields.One2many(
        'stock.reserved', 'consumed_in_mo_id',
        string="Sale-Reserved Components",
        help="Reserved products from the source sale order line that were "
             "added as extra components to this MO.")
    has_pending_reservations = fields.Boolean(
        compute='_compute_has_pending_reservations',
        string='Has Pending Reservations')
    auto_purchase_order_ids = fields.Many2many(
        'purchase.order',
        'mrp_production_auto_po_rel',
        'mrp_production_id', 'purchase_order_id',
        string='Auto-Generated POs',
        help="Purchase orders automatically created to cover product "
             "shortages for this MO.")
    auto_purchase_order_count = fields.Integer(
        compute='_compute_auto_purchase_order_count',
        string='Auto PO Count')

    # ============================================================
    # RAW MATERIALS READY NOTIFICATION
    # ============================================================

    raw_materials_ready_notified = fields.Boolean(
        string="Raw Materials Ready Notification Sent",
        default=False, copy=False, readonly=True,
        help="Set to True once the 'All Raw Materials Ready' notification "
             "has been fired for this MO. Prevents duplicate notifications.")

    def _are_all_raw_materials_ready(self):
        """Return True if every raw-material move on this MO is fully
        assigned (reserved). A move is ready when state='assigned' AND
        the reserved quantity covers the requested quantity."""
        self.ensure_one()
        if not self.move_raw_ids:
            return False
        if self.state in ('done', 'cancel', 'draft'):
            return False
        for move in self.move_raw_ids:
            if move.state == 'cancel':
                continue
            if move.state != 'assigned':
                return False
            reserved = sum(move.move_line_ids.mapped('quantity'))
            if reserved < move.product_uom_qty:
                return False
        return True

    def _check_and_notify_raw_materials_ready(self):
        """Check readiness on each MO; if fully ready and not yet notified,
        fire the email + chatter notification. Idempotent via the
        raw_materials_ready_notified flag."""
        for rec in self:
            if rec.raw_materials_ready_notified:
                continue
            if rec.state in ('done', 'cancel', 'draft'):
                continue
            if not rec._are_all_raw_materials_ready():
                continue
            try:
                rec._send_raw_materials_ready_notification()
                rec.raw_materials_ready_notified = True
            except Exception as e:
                _logger.exception(
                    "sales_stock_reservation: failed to send 'materials "
                    "ready' notification for MO %s: %s",
                    rec.display_name, e)

    def _send_raw_materials_ready_notification(self):
        """Build HTML body and email it to storekeepers + SO salesperson.
        Also post chatter messages on the MO and the linked SO."""
        self.ensure_one()

        # ------------------------------------------------------------------
        # Find the source SO line + order for context
        # ------------------------------------------------------------------
        so_line = self._find_source_sale_order_line()
        sale_order = so_line.order_id if so_line else False

        # ------------------------------------------------------------------
        # Build the components table rows
        # ------------------------------------------------------------------
        rows_html = "".join([
            "<tr>"
            "<td style='padding:4px 8px;border:1px solid #ddd;'>%s</td>"
            "<td style='padding:4px 8px;border:1px solid #ddd;text-align:right;'>%s</td>"
            "<td style='padding:4px 8px;border:1px solid #ddd;'>%s</td>"
            "<td style='padding:4px 8px;border:1px solid #ddd;text-align:center;'>"
            "<span style='color:green;font-weight:bold;'>&#10004; Ready</span></td>"
            "</tr>" % (
                move.product_id.display_name,
                move.product_uom_qty,
                move.product_uom.name or '',
            )
            for move in self.move_raw_ids if move.state != 'cancel'
        ])

        # ------------------------------------------------------------------
        # Build the full email body
        # ------------------------------------------------------------------
        body_html = (
                        "<p><span style='color:green;font-size:16px;'>&#10004;</span> "
                        "<strong>All raw materials are now ready for production.</strong></p>"
                        "<p>Manufacturing Order <strong>%s</strong> "
                        "(Product: <strong>%s</strong>, Qty: <strong>%s %s</strong>) "
                        "has all components fully reserved at the source location. "
                        "Production can begin.</p>"
                        "<p><strong>Source Sale Order:</strong> %s<br/>"
                        "<strong>Customer:</strong> %s</p>"
                        "<table style='border-collapse:collapse;margin-top:8px;'>"
                        "<thead><tr>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Component</th>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Required Qty</th>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>UoM</th>"
                        "<th style='padding:4px 8px;border:1px solid #ddd;background:#f5f5f5;'>Status</th>"
                        "</tr></thead>"
                        "<tbody>%s</tbody>"
                        "</table>"
                        "<p style='margin-top:12px;'>Please proceed to schedule the "
                        "production run.</p>"
                    ) % (
                        self.name,
                        self.product_id.display_name,
                        self.product_uom_qty,
                        self.product_uom_id.name or '',
                        sale_order.name if sale_order else '—',
                        sale_order.partner_id.display_name if sale_order else '—',
                        rows_html,
                    )

        subject = _(
            "All Raw Materials Ready: %s"
        ) % self.name

        # ------------------------------------------------------------------
        # Collect recipient emails
        # ------------------------------------------------------------------
        recipient_emails = []

        # Storekeepers: all internal users in the Inventory User group
        try:
            stock_group = self.env.ref(
                'stock.group_stock_user', raise_if_not_found=False)
            if stock_group:
                for user in stock_group.users:
                    if user.partner_id.email and \
                            user.partner_id.email not in recipient_emails:
                        recipient_emails.append(user.partner_id.email)
        except Exception:
            pass

        # SO salesperson
        if sale_order and sale_order.user_id and \
                sale_order.user_id.partner_id.email and \
                sale_order.user_id.partner_id.email not in recipient_emails:
            recipient_emails.append(sale_order.user_id.partner_id.email)

        # MO's responsible user (if different)
        if self.user_id and self.user_id.partner_id.email and \
                self.user_id.partner_id.email not in recipient_emails:
            recipient_emails.append(self.user_id.partner_id.email)

        # ------------------------------------------------------------------
        # Send the email
        # ------------------------------------------------------------------
        if recipient_emails:
            try:
                self.env['mail.mail'].sudo().create({
                    'subject': subject,
                    'body_html': body_html,
                    'email_to': ", ".join(recipient_emails),
                    'auto_delete': True,
                }).send()
            except Exception as e:
                _logger.warning(
                    "sales_stock_reservation: failed to send 'materials "
                    "ready' email for MO %s: %s", self.name, e)

        # ------------------------------------------------------------------
        # Post chatter message on the MO
        # ------------------------------------------------------------------
        from markupsafe import Markup
        self.message_post(
            body=Markup(body_html),
            subject=subject,
        )

        # ------------------------------------------------------------------
        # Post a brief chatter message on the linked SO
        # ------------------------------------------------------------------
        if sale_order:
            so_body = (
                          "<p><span style='color:green;font-size:16px;'>&#10004;</span> "
                          "All raw materials are ready for MO <strong>%s</strong>. "
                          "Production can begin.</p>"
                      ) % self.name
            sale_order.message_post(
                body=Markup(so_body),
                subject="MO %s — Materials Ready" % self.name,
            )

        _logger.info(
            "sales_stock_reservation: sent 'all raw materials ready' "
            "notification for MO %s.", self.name)


    def _compute_auto_purchase_order_count(self):
        for rec in self:
            rec.auto_purchase_order_count = len(rec.auto_purchase_order_ids)

    def _compute_has_pending_reservations(self):
        for rec in self:
            line = rec._find_source_sale_order_line()
            if line:
                pending = line.reserved_ids.filtered(
                    lambda r: r.state == 'reserved'
                    and not r.consumed_in_mo_id)
                rec.has_pending_reservations = bool(pending)
            else:
                rec.has_pending_reservations = False

    # ------------------------------------------------------------------
    # AUTO-INJECTION at multiple points
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        for production in productions:
            production._safe_inject_reserved_components(stage='create')
        return productions

    def action_confirm(self):
        res = super().action_confirm()
        for production in self:
            production._safe_inject_reserved_components(stage='action_confirm')
        return res

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'confirmed':
            for production in self:
                production._safe_inject_reserved_components(
                    stage='write_state_confirmed')
        return res

    def _safe_inject_reserved_components(self, stage='manual'):
        """Wrapper that catches exceptions so MO creation/confirmation flow
        is never blocked by this module."""
        for rec in self:
            try:
                rec._add_sale_reserved_components(stage=stage)
            except Exception as e:
                _logger.exception(
                    "sales_stock_reservation: stage=%s MO=%s failed: %s",
                    stage, rec.display_name, e)

    # ------------------------------------------------------------------
    # MANUAL BUTTON (for the user to click on the MO)
    # ------------------------------------------------------------------
    def action_inject_reserved_components(self):
        """Manual trigger - user clicks the button on the MO form."""
        for rec in self:
            count_before = len(rec.move_raw_ids)
            rec._add_sale_reserved_components(stage='manual_button')
            count_after = len(rec.move_raw_ids)
            added = count_after - count_before
            if added <= 0:
                so_line = rec._find_source_sale_order_line()
                if not so_line:
                    raise UserError(_(
                        "Could not find any Sale Order line linked to this "
                        "Manufacturing Order. The reservation cannot be "
                        "applied automatically.\n\n"
                        "MO origin: %s\nMO product: %s\n\n"
                        "Tip: make sure the SO has reservations and is the "
                        "source of this MO."
                    ) % (rec.origin or '', rec.product_id.display_name))
                pending = so_line.reserved_ids.filtered(
                    lambda r: r.state == 'reserved'
                    and not r.consumed_in_mo_id)
                if not pending:
                    raise UserError(_(
                        "No pending reservations on the linked SO line "
                        "(%s). They may already have been consumed by "
                        "another MO."
                    ) % so_line.display_name)
                raise UserError(_(
                    "No components were injected. Check the Reservation "
                    "Location is configured in Settings → Inventory → "
                    "Stock Reserve Location."))
        return True

    # ------------------------------------------------------------------
    # CORE INJECTION
    # ------------------------------------------------------------------
    def _add_sale_reserved_components(self, stage='unknown'):
        """Find the SO line that triggered this MO and append its reserved
        products as extra components (move_raw_ids).

        Idempotent: each reservation is moved only once thanks to the
        consumed_in_mo_id check.
        """
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            _logger.info(
                "sales_stock_reservation: MO %s in state %s; skip.",
                self.display_name, self.state)
            return

        so_line = self._find_source_sale_order_line()
        _logger.info(
            "sales_stock_reservation [stage=%s]: MO=%s origin=%s "
            "product=%s -> found SO line: %s",
            stage, self.display_name, self.origin,
            self.product_id.display_name,
            so_line.display_name if so_line else 'NONE')

        if not so_line:
            return

        reservations = so_line.reserved_ids.filtered(
            lambda r: r.state == 'reserved' and not r.consumed_in_mo_id)
        if not reservations:
            _logger.info(
                "sales_stock_reservation: SO line %s has no pending "
                "reservations.", so_line.display_name)
            return

        destination_id = self.env['ir.config_parameter'].sudo().get_param(
            'sales_stock_reservation.destination_location_id')
        if not destination_id:
            _logger.warning(
                "sales_stock_reservation: MO %s: reservations exist but "
                "no Reservation Location configured.", self.name)
            return
        reservation_location = self.env['stock.location'].browse(
            int(destination_id))

        new_move_vals = []
        for res in reservations:
            new_move_vals.append({
                'product_id': res.product_id.id,
                'product_uom_qty': res.reserved_quantity,
                'product_uom': res.product_uom_id.id,
                'location_id': reservation_location.id,
                'location_dest_id': self.production_location_id.id,
                'raw_material_production_id': self.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'warehouse_id': (self.location_src_id.warehouse_id.id
                                 if self.location_src_id else False),
                'procure_method': 'make_to_stock',
            })

        if not new_move_vals:
            return

        moves = self.env['stock.move'].create(new_move_vals)

        if self.state in ('confirmed', 'progress', 'to_close'):
            try:
                moves._action_confirm(merge=False)
                moves._action_assign()
            except Exception as e:
                _logger.warning(
                    "sales_stock_reservation: failed to confirm/assign "
                    "newly-injected moves on MO %s: %s", self.name, e)

        for res, move in zip(reservations, moves):
            res.consumed_in_mo_id = self.id
            res._safe_link_move_to_reservation(move)
        _logger.info(
            "sales_stock_reservation: injected %d components into MO %s.",
            len(moves), self.name)

    # ------------------------------------------------------------------
    # PRE-DONE Qty On Hand CHECK → AUTO PO
    # ------------------------------------------------------------------
    def button_mark_done(self):
        """Pre-check Qty on Hand for the finished product and all components.
        For any product where Qty On Hand <= 0, auto-create a PO BEFORE
        finishing the MO. Then proceed with the standard Done flow."""
        for production in self:
            try:
                production._auto_create_po_before_done()
            except Exception as e:
                _logger.exception(
                    "sales_stock_reservation: pre-done PO check failed "
                    "for MO %s: %s", production.display_name, e)
        res = super().button_mark_done()
        for production in self:
            production.sale_reserved_ids.write({'state': 'consumed'})
        return res

    def _auto_create_po_before_done(self):
        """Pre-Done check: for each product on the MO (Product field +
        Component lines), if Qty On Hand is <= 0, auto-create a PO for
        that product. The PO vendor is set to the source Sale Order's
        customer (partner_id)."""
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            return

        _logger.info(
            "sales_stock_reservation: ===== pre-done PO check START "
            "MO %s =====", self.display_name)

        self.env.invalidate_all()

        deficits = []  # list of (product, qty_needed)
        seen_product_ids = set()

        # ---- Check the FINISHED product (Product field on the MO) ----
        if self.product_id and \
                self.product_id.id not in seen_product_ids:
            seen_product_ids.add(self.product_id.id)
            self._check_product_for_deficit(
                self.product_id, self.product_uom_qty, deficits,
                role='finished')

        # ---- Check every COMPONENT (raw material) ----
        for move in self.move_raw_ids:
            product = move.product_id
            if not product or product.id in seen_product_ids:
                continue
            seen_product_ids.add(product.id)
            self._check_product_for_deficit(
                product, move.product_uom_qty, deficits,
                role='component')

        if not deficits:
            _logger.info(
                "sales_stock_reservation: MO %s — all products have "
                "stock, no PO needed.", self.name)
            return

        _logger.info(
            "sales_stock_reservation: deficits = %s",
            [(p.display_name, q) for p, q in deficits])

        # Get the SO's customer to use as PO vendor
        so_line = self._find_source_sale_order_line()
        so_customer = so_line.order_id.partner_id if so_line else False

        if not so_customer:
            _logger.warning(
                "sales_stock_reservation: MO %s — could not determine "
                "SO customer to use as PO vendor; skipping auto-PO.",
                self.name)
            self.message_post(body=_(
                "Auto-PO skipped — could not determine the source Sale "
                "Order's customer for these products: %s"
            ) % ", ".join(p.display_name for p, _q in deficits))
            return

        # Build PO lines (all deficits go into one PO under the SO customer)
        po_lines = []
        for product, qty in deficits:
            # Use the product's first seller for price reference (if any)
            seller = product.seller_ids[:1] if product.seller_ids else False
            price = seller.price if seller and seller.price else \
                product.standard_price
            po_lines.append((0, 0, {
                'product_id': product.id,
                'product_qty': qty,
                'product_uom_id': product.uom_id.id,
                'price_unit': price,
                'date_planned': fields.Datetime.now(),
            }))

        created_pos = self.env['purchase.order']
        try:
            po = self.env['purchase.order'].create({
                'partner_id': so_customer.id,
                'origin': self.name,
                'order_line': po_lines,
            })
            created_pos |= po
            _logger.info(
                "sales_stock_reservation: created PO %s vendor=%s "
                "(SO customer)",
                po.name, so_customer.display_name)
        except Exception as e:
            _logger.exception(
                "sales_stock_reservation: PO creation failed for "
                "customer-as-vendor %s: %s",
                so_customer.display_name, e)

        if created_pos:
            self.auto_purchase_order_ids = [
                (4, po.id) for po in created_pos]
            self.message_post(body=_(
                "Auto-generated Purchase Order(s) for products with "
                "insufficient stock: %s"
            ) % ", ".join(created_pos.mapped('name')))

        _logger.info(
            "sales_stock_reservation: ===== pre-done PO check END "
            "MO %s =====", self.display_name)

    def _check_product_for_deficit(self, product, required_qty, deficits,
                                   role='component'):
        """Helper: check a single product's company-wide Qty On Hand.
        If on-hand <= 0, append to deficits list. The qty_to_buy is the
        required quantity (so the MO can complete) plus the absolute
        amount needed to bring stock back to 0 if it is negative.
        """
        if hasattr(product, 'is_storable') and not product.is_storable:
            _logger.info(
                "sales_stock_reservation: skip %s %s (not storable)",
                role, product.display_name)
            return

        on_hand = product.with_company(self.company_id).qty_available
        _logger.info(
            "sales_stock_reservation: %s %s qty_on_hand=%s required=%s",
            role, product.display_name, on_hand, required_qty)

        if on_hand <= 0:
            # If qty_on_hand is 0   -> buy required_qty
            # If qty_on_hand is -2  -> buy required_qty + 2
            qty_to_buy = required_qty + abs(on_hand) if on_hand < 0 \
                else required_qty
            deficits.append((product, qty_to_buy))

    def action_view_auto_purchase_orders(self):
        """Smart-button action: open the auto-generated POs."""
        self.ensure_one()
        return {
            'name': _('Auto-Generated POs'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.auto_purchase_order_ids.ids)],
        }

    # ------------------------------------------------------------------
    # SOURCE SO-LINE LOOKUP
    # ------------------------------------------------------------------
    def _find_source_sale_order_line(self):
        """Locate the originating SO line for this MO using multiple
        strategies (works for Odoo 19 stock.reference and the legacy
        stock-move chain)."""
        self.ensure_one()
        SaleOrderLine = self.env['sale.order.line']

        # --- A) Downstream finished-move chain ---
        for fm in self.move_finished_ids:
            for dest in fm.move_dest_ids:
                if getattr(dest, 'sale_line_id', False):
                    return dest.sale_line_id
                for dest2 in dest.move_dest_ids:
                    if getattr(dest2, 'sale_line_id', False):
                        return dest2.sale_line_id

        # --- B) stock.reference (Odoo 19) ---
        if 'stock.reference' in self.env:
            try:
                refs = self.env['stock.reference'].sudo().search([
                    ('destination_model', '=', 'mrp.production'),
                    ('destination_id', '=', self.id),
                ])
                for ref in refs:
                    if ref.source_model == 'sale.order.line':
                        line = SaleOrderLine.browse(
                            ref.source_id).exists()
                        if line:
                            return line
                    if ref.source_model == 'sale.order':
                        order = self.env['sale.order'].browse(
                            ref.source_id).exists()
                        if order:
                            match = self._pick_so_line_from_order(order)
                            if match:
                                return match
            except Exception:
                pass

        # --- C) Origin lookup ---
        if self.origin:
            order = self.env['sale.order'].search(
                [('name', '=', self.origin)], limit=1)
            if order:
                match = self._pick_so_line_from_order(order)
                if match:
                    return match

        # --- D) Last resort: search any recent SO with reservations ---
        recent_orders = self.env['sale.order'].search([
            ('reserved_ids', '!=', False),
            ('state', 'in', ['sale', 'done']),
            ('apply_stock_reservation', '=', True),
        ], limit=50, order='id desc')
        for order in recent_orders:
            match = self._pick_so_line_from_order(order)
            if match:
                return match

        return SaleOrderLine

    def _pick_so_line_from_order(self, order):
        """From a SO, pick the line that has pending reservations and
        whose product matches this MO's product if possible."""
        self.ensure_one()
        SaleOrderLine = self.env['sale.order.line']
        lines_with_res = order.order_line.filtered(
            lambda l: l.reserved_ids.filtered(
                lambda r: r.state == 'reserved'
                and not r.consumed_in_mo_id))
        if not lines_with_res:
            return SaleOrderLine
        matched = lines_with_res.filtered(
            lambda l: l.product_id == self.product_id)
        if matched:
            return matched[:1]
        if len(lines_with_res) == 1:
            return lines_with_res
        return SaleOrderLine

    # ------------------------------------------------------------------
    # CANCEL
    # ------------------------------------------------------------------
    def action_cancel(self):
        res = super().action_cancel()
        for production in self:
            for reserved in production.sale_reserved_ids:
                reserved._return_reserved_stock()
        return res