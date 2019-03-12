# -*- coding: utf-8 -*-
# Author(s): Andrea Colangelo (andreacolangelo@openforce.it)
# Copyright 2018 Openforce Srls Unipersonale (www.openforce.it)
# Copyright 2018 Sergio Corato (https://efatto.it)
# Copyright 2018 Lorenzo Battistini <https://github.com/eLBati>
# Copyright 2018-2019 Matteo Boscolo (OmniaSolutions.eu)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import os
import logging
import base64
import shutil
import glob
from odoo import api, models, _

_logger = logging.getLogger(__name__)

FATTURAPA_IN_REGEX = "^[A-Z]{2}[a-zA-Z0-9]{11,16}_[a-zA-Z0-9]{,5}.(xml|zip)"
RESPONSE_MAIL_REGEX = '[A-Z]{2}[a-zA-Z0-9]{11,16}_[a-zA-Z0-9]{,5}_MT_' \
                      '[a-zA-Z0-9]{,3}'

#  for automation: env["fatturapa.ftp"].get_xml_customer_invoice()


class FTP_PA(models.AbstractModel):
    _name = "fatturapa.ftp"
    _inherit = 'mail.thread'

    def move_to_old(self, file_name):
        file_path = os.path.dirname(file_name)
        old_path = os.path.join(file_path, 'OLD')
        if not os.path.exists(old_path):
            os.mkdir(old_path)
        shutil.move(file_name, os.path.join(old_path, os.path.basename(file_name)))

    @api.model
    def create_fatturapa_in(self, file_path):
        fatturapa_attachment_in = self.env['fatturapa.attachment.in']
        file_name = os.path.basename(file_path)
        try:
            fatturapa_atts = fatturapa_attachment_in.search([('name', '=', file_name)])
            if fatturapa_atts:
                _logger.info(
                    "Invoice xml already processed in %s"
                    % fatturapa_atts.mapped('name'))
            else:
                with open(file_path, 'rb') as f:
                    fatturapa_attachment_in.create({'name': file_name,
                                                    'datas_fname': file_name,
                                                    'datas': base64.encodestring(f.read())})
                self.move_to_old(file_path)
        except Exception as ex:
            logging.error("Unable to load the electronic invoice %s" % file_name)
            logging.error("File %r" % file_path)
            logging.error("%r" % ex)

    @api.model
    def get_xml_customer_invoice(self):
        for xml_file in glob.glob(os.path.join(self.pa_in_folder, "FROM_SDI/*.xml")):
            _logger.info("Processing FatturaPA FTP file: %r" % xml_file)
            self.create_fatturapa_in(xml_file)

    @property
    @api.model
    def pa_in_folder(self):
        out = '/tmp'
        try:
            folder_from = False
            sdi_channel_id = self.env.user.company_id.sdi_channel_id
            if sdi_channel_id.channel_type == 'ftp':
                folder_from = sdi_channel_id.folder_to_sdi
            if not folder_from:
                logging.error("Unable to retrieve information for folder from")
            if not os.path.exists(folder_from):
                os.mkdir(folder_from)
            out = folder_from
        except Exception as ex:
            logging.error("Unable to get config parameter FATTURA_PA_IN %r" % ex)
        return out
