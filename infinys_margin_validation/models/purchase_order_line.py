# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _register_hook(self):
        res = super()._register_hook()
        self.env.cr.execute("""
            ALTER TABLE purchase_order_line
                ADD COLUMN IF NOT EXISTS required_margin NUMERIC DEFAULT 0.0;
        """)
        self.env.cr.execute("""
            ALTER TABLE purchase_order_line
                ADD COLUMN IF NOT EXISTS savings_percentage NUMERIC DEFAULT 0.0;
        """)
        return res

    required_margin = fields.Float(
        string="Required Margin (%)",
        digits=(5, 2),
        default=0.0,
        help="Desired gross margin on the selling price.\n"
             "Formula: Selling Price = Vendor Cost / (1 − Margin%)\n"
             "Example: Cost ₹100 at 40% → Selling Price = ₹166.67",
    )

    margin_percentage = fields.Float(
        string="Margin (%)",
        compute='_compute_margin_percentage',
        store=True,
        digits=(5, 2),
        help="Live gross margin: (Selling Price − Vendor Cost) / Selling Price × 100",
    )

    # FIX: was showing 4000% because _calc_margin_pct already returns a %
    # value (e.g. 40.0), but it was being multiplied by 100 again elsewhere.
    # Now computed alongside margin_percentage — result stored directly as-is.
    savings_percentage = fields.Float(
        string="Savings %",
        compute='_compute_margin_percentage',
        store=True,
        digits=(5, 2),
        help="(Selling Price − Vendor Cost) / Selling Price × 100\n"
             "Same formula as Margin (%). Stored directly — never ×100 again.",
    )

    is_margin_below_threshold = fields.Boolean(
        string="Margin Below Threshold",
        compute='_compute_margin_percentage',
        store=True,
    )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_selling_price(cost, margin_pct):
        """Selling Price = Cost / (1 − Margin%)"""
        if margin_pct >= 100.0:
            raise ValidationError(
                "Required Margin cannot be 100% or more — "
                "the selling price would be infinite."
            )
        if margin_pct < 0.0:
            raise ValidationError("Required Margin cannot be negative.")
        if margin_pct == 0.0:
            return cost
        return cost / (1.0 - margin_pct / 100.0)

    @staticmethod
    def _calc_margin_pct(selling_price, cost):
        if selling_price <= 0 or cost <= 0:  # ← guard zero cost
            return 0.0
        return ((selling_price - cost) / selling_price) * 100.0

    # ── UI Onchanges (bidirectional) ──────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id_margin(self):
        for line in self:
            if not line.product_id:
                continue
            threshold = self.env['margin.threshold.config'].search([
                ('category_id', '=', line.product_id.categ_id.id),
                ('company_id', '=', line.order_id.company_id.id),  # ← must be order's company, no fallback
                ('type', '=', 'vendor'),
            ], order='id desc', limit=1)
            if threshold:
                line.required_margin = threshold.minimum_margin
                cost = line.price_unit or 0.0
                if cost and threshold.minimum_margin:
                    try:
                        line.customer_price = self._calc_selling_price(
                            cost, threshold.minimum_margin
                        )
                    except ValidationError:
                        pass

    @api.onchange('required_margin', 'price_unit')
    def _onchange_required_margin(self):
        for line in self:
            cost = line.price_unit or 0.0
            margin = line.required_margin or 0.0
            if not cost:
                return  # ← stop here, no cost yet
            if margin >= 100.0:
                return  # ← don't compute, let user fix margin first
            line.customer_price = self._calc_selling_price(cost, margin)

    @api.onchange('customer_price')
    def _onchange_customer_price(self):
        for line in self:
            sp = line.customer_price or 0.0
            cost = line.price_unit or 0.0
            line.required_margin = self._calc_margin_pct(sp, cost)

    # ── Programmatic hooks (create / write) ───────────────────────────────────

    def _get_threshold_margin(self, categ_id, company_id):
        if not categ_id:
            return 0.0
        # Always use the order's company, never fall back to env.company
        # to avoid cross-company threshold matches
        threshold = self.env['margin.threshold.config'].search([
            ('category_id', '=', categ_id),
            ('company_id', '=', company_id),  # ← remove the `or self.env.company.id` fallback
            ('type', '=', 'vendor'),
        ], order='id desc', limit=1)
        return threshold.minimum_margin if threshold else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            cp = vals.get('customer_price') or 0.0
            pu = vals.get('price_unit') or 0.0

            if 'required_margin' not in vals or not vals.get('required_margin'):
                product_id = vals.get('product_id')
                if product_id:
                    product = self.env['product.product'].browse(product_id)
                    order_id = vals.get('order_id')
                    company_id = False
                    if order_id:
                        order = self.env['purchase.order'].browse(order_id)
                        company_id = order.company_id.id
                    threshold_margin = self._get_threshold_margin(
                        product.categ_id.id, company_id
                    )
                    if threshold_margin:
                        vals['required_margin'] = threshold_margin
                        if pu and not cp:
                            try:
                                vals['customer_price'] = self._calc_selling_price(
                                    pu, threshold_margin
                                )
                            except ValidationError:
                                pass

            if cp and 'required_margin' not in vals:
                pu = vals.get('price_unit') or 0.0
                if pu:  # ← only back-fill if cost is known
                    vals['required_margin'] = self._calc_margin_pct(cp, pu)
            elif vals.get('required_margin') and pu and not cp:
                try:
                    vals['customer_price'] = self._calc_selling_price(
                        pu, vals['required_margin']
                    )
                except ValidationError:
                    pass
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'customer_price' in vals or 'price_unit' in vals:
            if 'customer_price' in vals and 'required_margin' not in vals:
                cp = vals.get('customer_price') or 0.0
                for line in self:
                    pu = line.price_unit or 0.0
                    line.required_margin = self._calc_margin_pct(cp, pu)
            self._compute_margin_percentage()
        return res

    # ── Stored compute ────────────────────────────────────────────────────────

    @api.depends(
        'price_unit',
        'required_margin',
        'product_id.categ_id',
        'display_type',
        'is_downpayment',
    )
    def _compute_margin_percentage(self):
        ThresholdConfig = self.env['margin.threshold.config']
        for line in self:
            if line.display_type or line.is_downpayment:
                line.margin_percentage = 0.0
                line.savings_percentage = 0.0
                line.is_margin_below_threshold = False
                continue

            selling_price = getattr(line, 'customer_price', 0.0) or 0.0
            vendor_cost = line.price_unit or 0.0

            # _calc_margin_pct returns e.g. 40.0 for 40% — store directly.
            # Do NOT multiply by 100 again (that caused the 4000% bug).
            computed_margin = self._calc_margin_pct(selling_price, vendor_cost)
            line.margin_percentage = computed_margin
            line.savings_percentage = computed_margin

            threshold = ThresholdConfig.search([
                ('category_id', '=', line.product_id.categ_id.id),
                ('company_id', '=', line.order_id.company_id.id),  # ← order's company only
                ('type', '=', 'vendor'),
            ], order='id desc', limit=1)

            line.is_margin_below_threshold = bool(
                threshold
                and line.margin_percentage < threshold.minimum_margin
            )