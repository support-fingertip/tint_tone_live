# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    inv_expense_is_account_manager = fields.Boolean(
        compute='_compute_inv_expense_groups',
    )

    @api.depends_context('uid')
    def _compute_inv_expense_groups(self):
        is_account_manager = self.env.user.has_group('account.group_account_manager')
        for expense in self:
            expense.inv_expense_is_account_manager = is_account_manager

    @api.depends_context('uid')
    @api.depends('employee_id', 'state')
    def _compute_can_approve(self):
        super()._compute_can_approve()
        if not self.env.user.has_group('account.group_account_manager'):
            return

        for expense in self:
            if expense.state in {'draft', 'submitted', 'approved'}:
                expense.can_approve = True

    def _can_be_autovalidated(self):
        if (
            self.env.user.has_group('account.group_account_invoice')
            and not self.env.user.has_group('account.group_account_manager')
        ):
            return False
        return super()._can_be_autovalidated()

    def action_submit(self):
        if self.env.user.has_group('account.group_account_manager'):
            raise UserError("Accounts managers should approve expenses directly.")
        if not self.env.user.has_group('account.group_account_invoice'):
            raise UserError("Only account associates can submit expenses for approval.")
        return super().action_submit()

    def action_approve(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError("Only accounts managers can approve expenses.")
        return super().action_approve()

    def action_refuse(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError("Only accounts managers can refuse expenses.")
        return super().action_refuse()

    def _do_approve(self, check=True):
        if not self.env.user.has_group('account.group_account_manager'):
            return super()._do_approve(check=check)

        if check:
            self._check_can_approve()
        expenses_to_approve = self.filtered(lambda expense: expense.state in {'submitted', 'draft'})
        for expense in expenses_to_approve:
            expense.sudo().write({
                'approval_state': 'approved',
                'manager_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
        self.update_activities_and_mails()

    def _check_can_refuse(self):
        if self.env.user.has_group('account.group_account_manager'):
            return
        return super()._check_can_refuse()

    def _do_refuse(self, reason):
        if not self.env.user.has_group('account.group_account_manager'):
            return super()._do_refuse(reason)

        draft_moves_sudo = self.sudo().account_move_id.filtered(lambda move: move.state == 'draft')
        posted_moves_sudo = self.sudo().account_move_id - draft_moves_sudo
        if posted_moves_sudo:
            return super()._do_refuse(reason)

        if draft_moves_sudo:
            draft_moves_sudo.unlink()

        self.sudo().approval_state = 'refused'
        for expense in self:
            expense.message_post(body=reason)
        self.update_activities_and_mails()

    def _prepare_move_vals(self):
        vals = super()._prepare_move_vals()
        if all(expense.state == 'approved' for expense in self):
            vals['inv_receipt_approval_state'] = 'approved'
        return vals
