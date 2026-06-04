from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    disable_ask_ai_systray = fields.Boolean(
        string='Disable Ask AI Systray',
        default=False,
    )
