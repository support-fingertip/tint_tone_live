from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    disable_ask_ai_systray = fields.Boolean(
        related='company_id.disable_ask_ai_systray',
        readonly=False,
    )
