# -*- coding: utf-8 -*-
# Copyright 2016-2017 Lorenzo Battistini - Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.tools.misc import formatLang
from odoo.tools.translate import _
from odoo.exceptions import Warning as UserError

import time


class ReportRegistroIva(models.AbstractModel):
    _name = 'report.l10n_it_vat_registries.report_registro_iva'

    @api.model
    def render_html(self, docids, data=None):
        # docids required by caller but not used
        # see addons/account/report/account_balance.py

        date_format = data['form']['date_format']

        docargs = {
            'doc_ids': data['ids'],
            'doc_model': self.env['account.move'],
            'data': data['form'],
            'docs': self.env['account.move'].browse(data['ids']),
            'get_move': self._get_move,
            'tax_lines': self._get_tax_lines,
            'format_date': self._format_date,
            'from_date': self._format_date(
                data['form']['from_date'], date_format),
            'to_date': self._format_date(
                data['form']['to_date'], date_format),
            'registry_type': data['form']['registry_type'],
            'invoice_total': self._get_move_total,
            'tax_registry_name': data['form']['tax_registry_name'],
            'env': self.env,
            'formatLang': formatLang,
            'compute_totals_tax': self._compute_totals_tax,
            'l10n_it_count_fiscal_page_base': data['form']['fiscal_page_base'],
            'only_totals': data['form']['only_totals'],
            'date_format': date_format
        }

        return self.env['report'].render(
            'l10n_it_vat_registries.report_registro_iva', docargs)

    def _get_move(self, move_ids):
        move_list = self.env['account.move'].browse(move_ids)
        return move_list

    def _format_date(self, my_date, date_format):
        formatted_date = time.strftime(date_format,
                                       time.strptime(my_date, '%Y-%m-%d'))
        return formatted_date or ''

    def _get_invoice_from_move(self, move):
        return self.env['account.invoice'].search([
            ('move_id', '=', move.id)])

    def _get_move_line(self, move, data):
        return [move_line for move_line in move.line_ids]

    def _get_good_tax(self, move_line):
        tax = False
        is_base = True
        good_taxes = []
        excluded_taxes = []
        for tmptax in move_line.tax_ids:
            if tmptax.exclude_from_registries:
                excluded_taxes.append(tmptax)
                continue
            good_taxes.append(tmptax)
        if good_taxes and len(good_taxes) != 1:
                raise UserError(
                    _("Move line %s has too many base taxes")
                    % move_line.name)

        if good_taxes:
            tax = good_taxes[0]
            is_base = True
        else:
            tax = move_line.tax_line_id
            is_base = False
        return tax, is_base, excluded_taxes
        
    def _tax_amounts_by_tax_id(self, move, move_lines, registry_type):
        res = {}

        for move_line in move_lines:
            set_cee_absolute_value = False
            if not(move_line.tax_line_id or move_line.tax_ids):
                continue

            tax, is_base, _ = self._get_good_tax(move_line)
            if not tax:
                continue
            if (
                (registry_type == 'customer' and tax.cee_type == 'sale') or
                (registry_type == 'supplier' and tax.cee_type == 'purchase')
            ):
                set_cee_absolute_value = True

            elif tax.cee_type:
                continue

#             if tax.parent_tax_ids and len(tax.parent_tax_ids) == 1:
#                 # we group by main tax
#                 tax = tax.parent_tax_ids[0]

            if tax.exclude_from_registries:
                continue

            if not res.get(tax.id):
                res[tax.id] = {
                    'name': tax.name,
                    'base': 0,
                    'tax': 0,
                }
            tax_amount = move_line.debit - move_line.credit

            if set_cee_absolute_value:
                tax_amount = abs(tax_amount)

            if (
                'receivable' in move.move_type or
                ('payable_refund' == move.move_type and tax_amount > 0)
            ):
                # otherwise refund would be positive and invoices
                # negative.
                # We also check payable_refund as it normaly is < 0, but
                # it can be > 0 in case of reverse charge with VAT integration
                tax_amount = -tax_amount

            if is_base:
                # recupero il valore dell'imponibile
                res[tax.id]['base'] += tax_amount
            else:
                # recupero il valore dell'imposta
                res[tax.id]['tax'] += tax_amount

        return res

    def _get_tax_lines(self, move, data):
        """

        Args:
            move: the account.move representing the invoice

        Returns:
            A tuple of lists: (INVOICE_TAXES, TAXES_USED)
            where INVOICE_TAXES is a list of dict
            and TAXES_USED a recordset of account.tax

        """
        inv_taxes = []
        used_taxes = self.env['account.tax']

        # index è usato per non ripetere la stampa dei dati fattura quando ci
        # sono più codici IVA
        index = 0
        invoice = self._get_invoice_from_move(move)
        if 'refund' in move.move_type:
            invoice_type = "NC"
        else:
            invoice_type = "FA"

        move_lines = self._get_move_line(move, data)

        amounts_by_tax_id = self._tax_amounts_by_tax_id(
            move,
            move_lines,
            data['registry_type'])

        for tax_id in amounts_by_tax_id:
            tax = self.env['account.tax'].browse(tax_id)
            tax_item = {
                'tax_code_name': tax._get_tax_name(),
                'base': amounts_by_tax_id[tax_id]['base'],
                'tax': amounts_by_tax_id[tax_id]['tax'],
                'index': index,
                'invoice_type': invoice_type,
                'invoice_date': (
                    invoice and invoice.date_invoice or move.date or ''),
                'reference': (
                    invoice and invoice.reference or ''),
            }
            inv_taxes.append(tax_item)
            index += 1
            used_taxes |= tax

        return inv_taxes, used_taxes

    def _get_move_total(self, move):
        total = 0.0
        receivable_payable_found = False
        for move_line in move.line_ids:
            if move_line.account_id.internal_type == 'receivable':
                total += move_line.debit or (- move_line.credit)
                receivable_payable_found = True
            elif move_line.account_id.internal_type == 'payable':
                total += (- move_line.debit) or move_line.credit
                receivable_payable_found = True
        if receivable_payable_found:
            total = abs(total)
        else:
            total = abs(move.amount)
        if 'refund' in move.move_type:
            total = -total
        return total

#     def _get_move_total(self, move):
#         total = 0.0
#         receivable_payable_found = False
#         for move_line in move.line_ids:
#             tax, _is_base, _ = self._get_good_tax(move_line)
#             if move_line.account_id.internal_type == 'receivable':
#                 if tax:
#                     total += move_line.debit or (- move_line.credit)
#                     receivable_payable_found = True
#             elif move_line.account_id.internal_type == 'payable':
#                 if tax:
#                     total += (- move_line.debit) or move_line.credit
#                     receivable_payable_found = True
#         if receivable_payable_found:
#             total = abs(total)
#         else:
#             starting_amount = abs(move.amount)
#             for move_line in move.line_ids:
#                 _good_tax, _is_base, excluded_taxes = self._get_good_tax(move_line)
#                 for tax in excluded_taxes:
#                     res = tax.compute_all(move_line.product_id.list_price,
#                                           move_line.currency_id,
#                                           move_line.quantity,
#                                           product=move_line.product_id,
#                                           partner=move_line.partner_id)
#                     if res:
#                         taxes = res.get('taxes', [])
#                         for tax in taxes:
#                             starting_amount -= tax.get('amount', 0)
#             total = abs(starting_amount)
#         if 'refund' in move.move_type:
#             total = -total
#         return total

    def _compute_totals_tax(self, tax, data):
        """
        Returns:
            A tuple: (tax_name, base, tax, deductible, undeductible)

        """
        return tax._compute_totals_tax(data)
