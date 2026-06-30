from odoo import fields, models

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    dummy = fields.Char(string='Dummy Field')

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for payment in self:
            if payment.payment_type == 'inbound' and payment.partner_type == 'customer' and payment.partner_id:
                template = self.env.ref('invoice_receipt_approval.email_template_payment_receipt_custom', raise_if_not_found=False)
                if template:
                    template.send_mail(payment.id, force_send=True)
        return res
