# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def write(self, vals):
        """When a move's state changes to 'assigned' (fully reserved),
        check if the MO it belongs to is now fully ready and notify."""
        res = super().write(vals)
        if vals.get('state') == 'assigned':
            mo_ids = self.mapped('raw_material_production_id')
            if mo_ids:
                mo_ids._check_and_notify_raw_materials_ready()
        return res

    def _action_assign(self, force_qty=False):
        """Also catch assignments that happen without explicit state write."""
        res = super()._action_assign(force_qty=force_qty)
        mo_ids = self.mapped('raw_material_production_id')
        if mo_ids:
            mo_ids._check_and_notify_raw_materials_ready()
        return res
