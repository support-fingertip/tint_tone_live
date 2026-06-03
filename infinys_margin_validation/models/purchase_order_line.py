# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # =========================================================================
    # DB COLUMN BOOTSTRAP
    # _register_hook runs on EVERY server start (not just -u), so the column
    # is guaranteed to exist before any ORM create() hits the database.
    # =========================================================================

    def _register_hook(self):
        res = super()._register_hook()
        self.env.cr.execute("""
            ALTER TABLE purchase_order_line
                ADD COLUMN IF NOT EXISTS required_margin NUMERIC DEFAULT 0.0;
        """)
        return res

    # =========================================================================
    # GROSS MARGIN PRICING
    #
    # Formula : Selling Price = Vendor Cost / (1 − Margin%)
    # Example : Cost ₹100 @ 40% margin  →  100 / (1 − 0.40) = ₹166.67
    #
    # Fields involved
    #   price_unit      — vendor cost (what we PAY)          [existing]
    #   customer_price  — selling price (what we CHARGE)     [boq_management_v19]
    #   required_margin — desired gross margin %             [this module]
    #   margin_percentage — live gross margin (computed)     [this module]
    #
    # NOTE: customer_price is declared in boq_management_v19 which depends on
    # this module, so it cannot appear in @api.depends (circular load order).
    # It is accessed via getattr() in the compute body and re-triggered via
    # write() / create() overrides.
    # =========================================================================

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
    is_margin_below_threshold = fields.Boolean(
        string="Margin Below Threshold",
        compute='_compute_margin_percentage',
        store=True,
    )

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _calc_selling_price(cost, margin_pct):
        """Selling Price = Cost / (1 − Margin%)  — gross margin formula."""
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
        """Margin % = (SP − Cost) / SP × 100  — reverse gross margin."""
        if selling_price <= 0:
            return 0.0
        return ((selling_price - cost) / selling_price) * 100.0

    # =========================================================================
    # UI ONCHANGES  (bidirectional)
    # =========================================================================

    @api.onchange('product_id')
    def _onchange_product_id_margin(self):
        """
        When product changes, auto-load the Required Margin (%) from
        Vendor Margin Thresholds (margin.threshold.config) based on the
        product's category (Trade).  The existing price_unit onchange will
        then compute Selling Price automatically.
        """
        for line in self:
            if not line.product_id:
                continue
            threshold = self.env['margin.threshold.config'].search([
                ('category_id', '=', line.product_id.categ_id.id),
                ('company_id', '=', (line.order_id.company_id.id or self.env.company.id)),
            ], limit=1)
            if threshold:
                line.required_margin = threshold.minimum_margin
                # Also recompute selling price if cost is already known
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
        """
        User enters Required Margin (%) or changes Vendor Cost
        → auto-compute Selling Price (customer_price).

        Selling Price = Vendor Cost / (1 − Margin%)
        """
        for line in self:
            cost = line.price_unit or 0.0
            margin = line.required_margin or 0.0
            if not cost:
                continue
            line.customer_price = self._calc_selling_price(cost, margin)

    @api.onchange('customer_price')
    def _onchange_customer_price(self):
        """
        User enters Selling Price (customer_price) directly
        → back-fill Required Margin %.

        Margin % = (SP − Cost) / SP × 100
        """
        for line in self:
            sp = line.customer_price or 0.0
            cost = line.price_unit or 0.0
            line.required_margin = self._calc_margin_pct(sp, cost)

    # =========================================================================
    # PROGRAMMATIC HOOKS  (create / write)
    # Onchanges only fire in the UI; these ensure correctness when records are
    # created/updated by server-side code (e.g. BOQ → Create RFQ).
    # =========================================================================

    def _get_threshold_margin(self, categ_id, company_id):
        """Return minimum_margin from threshold config for a given category, or 0."""
        if not categ_id:
            return 0.0
        threshold = self.env['margin.threshold.config'].search([
            ('category_id', '=', categ_id),
            ('company_id', '=', company_id or self.env.company.id),
        ], limit=1)
        return threshold.minimum_margin if threshold else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            cp = vals.get('customer_price') or 0.0
            pu = vals.get('price_unit') or 0.0

            # Auto-load required_margin from threshold if not supplied
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
                        # Forward-fill customer_price from threshold margin + cost
                        if pu and not cp:
                            try:
                                vals['customer_price'] = self._calc_selling_price(
                                    pu, threshold_margin
                                )
                            except ValidationError:
                                pass

            # Back-fill required_margin from customer_price if still missing
            if cp and 'required_margin' not in vals:
                vals['required_margin'] = self._calc_margin_pct(cp, pu)
            # Forward-fill customer_price from required_margin if cost known
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
        # customer_price cannot be in @api.depends (see module-load note above).
        # Manually trigger the stored compute when relevant fields change.
        if 'customer_price' in vals or 'price_unit' in vals:
            # Also sync required_margin when customer_price is written directly
            if 'customer_price' in vals and 'required_margin' not in vals:
                cp = vals.get('customer_price') or 0.0
                for line in self:
                    pu = line.price_unit or 0.0
                    line.required_margin = self._calc_margin_pct(cp, pu)
            self._compute_margin_percentage()
        return res

    # =========================================================================
    # STORED COMPUTE  — margin_percentage & is_margin_below_threshold
    # =========================================================================

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
            # Skip section/note lines and down-payment lines
            if line.display_type or line.is_downpayment:
                line.margin_percentage = 0.0
                line.is_margin_below_threshold = False
                continue

            # customer_price lives in boq_management_v19 — access via getattr
            selling_price = getattr(line, 'customer_price', 0.0) or 0.0
            vendor_cost = line.price_unit or 0.0

            line.margin_percentage = self._calc_margin_pct(selling_price, vendor_cost)

            # Check against category-wise minimum threshold
            threshold = ThresholdConfig.search([
                ('category_id', '=', line.product_id.categ_id.id),
                ('company_id', '=', line.order_id.company_id.id),
            ], limit=1)

            line.is_margin_below_threshold = bool(
                threshold
                and line.margin_percentage < threshold.minimum_margin
            )
