from odoo import models, api, _
from odoo.exceptions import ValidationError

class BoqBoq(models.Model):
    _inherit = 'boq.boq'

    @api.constrains('line_ids', 'category_ids')
    def _check_boq_line_quantities(self):
        for boq in self:
            for line in boq.line_ids:
                if line.qty <= 0 and line.category_id in boq.category_ids:
                    raise ValidationError(_(
                        "Quantity cannot be zero or negative for the line '%s' in the enabled category '%s'."
                    ) % (line.product_id.display_name or 'Unknown', line.category_id.name))

    def action_create_rfq(self):
        for boq in self:
            for line in boq.line_ids:
                if line.qty <= 0 and line.category_id in boq.category_ids:
                    raise ValidationError(_(
                        "Cannot create RFQ: Quantity is zero or negative for the line '%s' in the enabled category '%s'."
                    ) % (line.product_id.display_name or 'Unknown', line.category_id.name))
        return super().action_create_rfq()
