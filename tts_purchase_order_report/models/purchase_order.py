# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    validity_end_date = fields.Date(string='Validity End Date')
    our_ref = fields.Char(string='Our Reference')
    freight_charge = fields.Monetary(
        string='Freight Charge',
        currency_field='currency_id',
    )
    packing_tax = fields.Monetary(
        string='Packing Tax',
        currency_field='currency_id',
    )
    remark = fields.Text(string='Remark')

    amount_cgst = fields.Monetary(
        string='CGST Amount',
        compute='_compute_gst_split',
        currency_field='currency_id',
    )
    amount_sgst = fields.Monetary(
        string='SGST Amount',
        compute='_compute_gst_split',
        currency_field='currency_id',
    )
    amount_gross = fields.Monetary(
        string='Gross Amount',
        compute='_compute_amount_gross',
        currency_field='currency_id',
    )

    @api.depends('order_line.tax_ids', 'order_line.price_subtotal', 'amount_tax')
    def _compute_gst_split(self):
        for order in self:
            cgst = sgst = 0.0
            for line in order.order_line:
                for tax in line.tax_ids:
                    name = (tax.name or '').upper()
                    tax_amt = line.price_subtotal * (tax.amount / 100.0) if tax.amount_type == 'percent' else 0.0
                    if 'CGST' in name:
                        cgst += tax_amt
                    elif 'SGST' in name:
                        sgst += tax_amt
            order.amount_cgst = cgst
            order.amount_sgst = sgst

    @api.depends('amount_total', 'freight_charge', 'packing_tax')
    def _compute_amount_gross(self):
        for order in self:
            order.amount_gross = (order.amount_total or 0.0) \
                + (order.freight_charge or 0.0) \
                + (order.packing_tax or 0.0)

    def amount_in_words(self):
        self.ensure_one()
        if not self.currency_id:
            return ''
        return self.currency_id.amount_to_text(self.amount_gross or self.amount_total)
