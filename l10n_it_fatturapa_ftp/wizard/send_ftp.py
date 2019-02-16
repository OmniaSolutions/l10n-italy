# -*- coding: utf-8 -*-
# Copyright 2019 Matteo Boscolo (https://OmniaSolutions.website
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, api


class SendFTP(models.TransientModel):
    _name = 'wizard.fatturapa.send.ftp'
    _description = "Wizard to send multiple e-invoice FTP"

    @api.multi
    def send_ftp(self):
        if self.env.context.get('active_ids'):
            attachments = self.env['fatturapa.attachment.out'].browse(
                self.env.context['active_ids'])
            attachments.send_via_ftp()
