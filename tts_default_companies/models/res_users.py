from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    default_enabled_company_ids = fields.Many2many(
        'res.company',
        'res_users_default_enabled_company_rel',
        'user_id',
        'company_id',
        string='Default Enabled Companies',
        domain="[('id', 'in', company_ids)]",
        help="Select the companies that should be enabled by default when this user logs in. They must be a subset of Allowed Companies."
    )
