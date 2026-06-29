from odoo import models

class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        res = super().session_info()
        res['disable_ask_ai_systray'] = self.env.company.disable_ask_ai_systray
        return res
