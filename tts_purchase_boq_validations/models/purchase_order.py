from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            if vals.get('date_order'):
                date_order = fields.Datetime.to_datetime(vals['date_order']).date()
                if date_order < today:
                    raise ValidationError(_("Order Date cannot be set to a past date."))
            if vals.get('validity_end_date'):
                validity_date = fields.Date.to_date(vals['validity_end_date'])
                if validity_date < today:
                    raise ValidationError(_("Validity End Date cannot be set to a past date."))
        return super().create(vals_list)

    def write(self, vals):
        today = fields.Date.context_today(self)
        if vals.get('date_order'):
            date_order = fields.Datetime.to_datetime(vals['date_order']).date()
            if date_order < today:
                raise ValidationError(_("Order Date cannot be set to a past date."))
        
        if vals.get('validity_end_date'):
            validity_date = fields.Date.to_date(vals['validity_end_date'])
            if validity_date < today:
                raise ValidationError(_("Validity End Date cannot be set to a past date."))

        if 'partner_id' in vals:
            for order in self:
                if order.state not in ('draft', 'cancel') and order.partner_id.id != vals['partner_id']:
                    raise ValidationError(_("You cannot change the vendor after the RFQ has been sent."))
        return super().write(vals)

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def write(self, vals):
        if 'product_qty' in vals:
            for line in self:
                if line.order_id.state not in ('draft', 'cancel'):
                    raise ValidationError(_("You cannot change the quantity after the purchase order has been sent."))
        return super().write(vals)

    @api.constrains('product_qty', 'price_unit')
    def _check_quantity_and_price(self):
        for line in self:
            if line.product_qty <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))
            if line.price_unit <= 0:
                raise ValidationError(_("Unit Price must be greater than zero."))

