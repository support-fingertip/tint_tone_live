# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    invoice_approval_active = fields.Boolean(
        string='Invoice, Bill, Credit/Debit Note Approval',
        help='Require associates to submit invoices, bills, credit notes, and debit notes for approval when total exceeds the minimum amount.',
    )
    invoice_approval_amount = fields.Monetary(
        string='Minimum Amount',
        help='Invoices, bills, credit notes, and debit notes with a total above this amount require approval from an administrator.',
    )
    receipt_approval_active = fields.Boolean(
        string='Receipt Approval',
        help='Require associates to submit receipts for approval when total exceeds the minimum amount.',
    )
    receipt_approval_amount = fields.Monetary(
        string='Minimum Receipt Amount',
        help='Receipts with a total above this amount require approval from an administrator.',
    )
