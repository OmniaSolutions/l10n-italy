# -*- coding: utf-8 -*-
# Author(s): Andrea Colangelo (andreacolangelo@openforce.it)
# Copyright 2018 Openforce Srls Unipersonale (www.openforce.it)
# Copyright 2018 Sergio Corato (https://efatto.it)
# Copyright 2018-2019 Lorenzo Battistini <https://github.com/eLBati>
# Copyright 2018-2019 Matteo Boscolo (OmniaSolutions.eu)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
import re
import os
import glob
import shutil
import hashlib
import sys
from lxml import etree
from odoo import api
from odoo import fields
from odoo import models
from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RESPONSE_MAIL_REGEX = '[A-Z]{2}[a-zA-Z0-9]{11,16}_[a-zA-Z0-9]{,5}_[A-Z]{2}_' \
                      '[a-zA-Z0-9]{,3}'


def sha256_checksum(filename, block_size=65536):
    sha256 = hashlib.sha256()
    with open(filename, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            sha256.update(block)
    return sha256.hexdigest()


class FatturaPAAttachmentOut(models.Model):
    _inherit = 'fatturapa.attachment.out'

    state = fields.Selection([('ready', 'Ready to Send'),
                              ('sent', 'Sent'),
                              ('sender_error', 'Sender Error'),
                              ('recipient_error', 'Not delivered'),
                              ('rejected', 'Rejected (PA)'),
                              ('validated', 'Delivered'),
                              ('accepted', 'Accepted'),
                              ],
                             string='State',
                             default='ready',)

    last_sdi_response = fields.Text(
        string='Last Response from Exchange System', default='No response yet',
        readonly=True)
    sending_date = fields.Datetime("Sent Date", readonly=True)
    delivered_date = fields.Datetime("Delivered Date", readonly=True)
    sending_user = fields.Many2one("res.users", "Sending User", readonly=True)
    file_hash = fields.Char("File Hash Number", readonly=True)

    @api.multi
    def reset_to_ready(self):
        for att in self:
            if att.state != 'sender_error':
                raise UserError(
                    _("You can only reset files in 'Sender Error' state.")
                )
            att.state = 'ready'

    @api.multi
    def send_via_ftp(self):
        for fatturapa_attachment_out_id in self:
            if fatturapa_attachment_out_id.state == 'ready':
                try:
                    logging.info('Send file to ftp %r' % fatturapa_attachment_out_id.datas_fname)
                    file_name = os.path.join(self.pa_in_folder, 'TO_SDI', fatturapa_attachment_out_id.datas_fname)
                    xml_content = fatturapa_attachment_out_id.datas.decode('base64')
                    with open(file_name, 'wb') as f:
                        f.write(xml_content)
                    fatturapa_attachment_out_id.file_hash = sha256_checksum(file_name)
                    fatturapa_attachment_out_id.state = 'sent'
                except Exception as ex:
                    logging.error(ex)
                    fatturapa_attachment_out_id.message_post(body="<b>Error sending to local FTP Folder</b>")
                    fatturapa_attachment_out_id.state = 'sender_error'

    @api.model
    def get_xml_sdi_responce(self):
        for xml_file in glob.glob(os.path.join(self.pa_in_folder, "FROM_SDI/*.xml")):
            _logger.info("Processing FatturaPA FTP file: %r" % xml_file)
            self.parse_xml_response(xml_file)

    @api.multi
    def parse_xml_response(self, xml_file):
        xml_file_name = os.path.basename(xml_file)
        with open(xml_file, 'rb') as datasXml:
            message_type = xml_file_name.split('_')[2]
            root = etree.parse(datasXml)
            file_name = root.find('NomeFile')
            fatturapa_attachment_out = False
            if file_name is not None:
                vals = {}
                file_name = file_name.text
                fatturapa_attachment_out = self.search(
                    ['|', ('datas_fname', '=', file_name),
                     ('datas_fname', '=', file_name.replace('.p7m', ''))])
                if len(fatturapa_attachment_out) > 1:
                    _logger.info('More than 1 out invoice found for incoming'
                                 'message')
                    fatturapa_attachment_out = fatturapa_attachment_out[0]
                if not fatturapa_attachment_out:
                    raise UserError("E-Invoice %r not found in the system" % file_name)

            id_sdi = root.find('IdentificativoSdI')
            receipt_dt = root.find('DataOraRicezione')
            message_id = root.find('MessageId')
            id_sdi = id_sdi.text if id_sdi is not None else False
            receipt_dt = receipt_dt.text if receipt_dt is not None \
                else False
            message_id = message_id.text if message_id is not None \
                else False
            if message_type == 'NS':  # 2A. Notifica di Scarto
                error_list = root.find('ListaErrori')
                error_str = ''
                for error in error_list:
                    error_str += u"\n[%s] %s %s" % (
                        error.find('Codice').text if error.find(
                            'Codice') is not None else '',
                        error.find('Descrizione').text if error.find(
                            'Descrizione') is not None else '',
                        error.find('Suggerimento').text if error.find(
                            'Suggerimento') is not None else ''
                    )
                vals = {'state': 'sender_error',
                        'last_sdi_response': u'SdI ID: {}; '
                        u'Message ID: {}; Receipt date: {}; '
                        u'Error: {}'.format(id_sdi,
                                            message_id,
                                            receipt_dt,
                                            error_str)}
            elif message_type == 'MC':  # 3A. Mancata consegna
                missed_delivery_note = root.find('Descrizione').text
                vals = {'state': 'recipient_error',
                        'last_sdi_response': u'SdI ID: {}; '
                        u'Message ID: {}; Receipt date: {}; '
                        u'Missed delivery note: {}'.format(id_sdi,
                                                           message_id,
                                                           receipt_dt,
                                                           missed_delivery_note)}
            elif message_type == 'RC':  # 3B. Ricevuta di Consegna
                delivery_dt = root.find('DataOraConsegna').text
                vals = {'state': 'validated',
                        'delivered_date': fields.Datetime.now(),
                        'last_sdi_response': 'SdI ID: {}; '
                        'Message ID: {}; Receipt date: {}; '
                        'Delivery date: {}'.format(id_sdi,
                                                   message_id,
                                                   receipt_dt,
                                                   delivery_dt)}
            elif message_type == 'NE':  # 4A. Notifica Esito per PA
                esito_committente = root.find('EsitoCommittente')
                if esito_committente is not None:
                    # more than one esito?
                    esito = esito_committente.find('Esito')
                    if esito is not None:
                        if esito.text == 'EC01':
                            state = 'validated'
                        elif esito.text == 'EC02':
                            state = 'rejected'
                        vals = {'state': state,
                                'last_sdi_response': u'SdI ID: {}; '
                                u'Message ID: {}; Response: {}; '.format(id_sdi,
                                                                         message_id,
                                                                         esito.text)}
            elif message_type == 'DT':  # 5. Decorrenza Termini per PA
                description = root.find('Descrizione')
                if description is not None:
                    vals = {'state': 'validated',
                            'last_sdi_response': u'SdI ID: {}; '
                            u'Message ID: {}; Receipt date: {}; '
                            u'Description: {}'.format(id_sdi,
                                                      message_id,
                                                      receipt_dt,
                                                      description.text)}
            # not implemented - todo
            elif message_type == 'AT':  # 6. Avvenuta Trasmissione per PA
                description = root.find('Descrizione')
                if description is not None:
                    vals = {'state': 'accepted',
                            'last_sdi_response': (
                                u'SdI ID: {}; Message ID: {}; '
                                u'Receipt date: {};'
                                u' Description: {}').format(id_sdi,
                                                            message_id,
                                                            receipt_dt,
                                                            description.text)}
            fatturapa_attachment_out.write(vals)
            body = vals.get('last_sdi_response', '')
            if vals.get('state') == 'validated':
                body = '<b style="color:green;">' + body + '</b>'
            else:
                body = '<b style="color:red;">' + body + '</b>'

            fatturapa_attachment_out.message_post(body=body,
                                                  attachments=[(xml_file_name,
                                                                etree.tostring(root))])
        self.move_to_old(xml_file)

    @api.multi
    def unlink(self):
        for att in self:
            if att.state != 'ready':
                raise UserError(_(
                    "You can only delete files in 'Ready to Send' state."
                ))
        return super(FatturaPAAttachmentOut, self).unlink()

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
                logging.error("Unable to retrive information for folder from")
            if not os.path.exists(folder_from):
                os.mkdir(folder_from)
            from_sdi = os.path.join(folder_from, 'FROM_SDI')
            if not os.path.exists(from_sdi):
                os.mkdir(from_sdi)
            to_sdi = os.path.join(folder_from, 'TO_SDI')
            if not os.path.exists(to_sdi):
                os.mkdir(to_sdi)
            out = folder_from
        except Exception as ex:
            logging.error("Unable to get config parameter FATTURA_PA_IN %r" % ex)
        return out

    def move_to_old(self, file_name):
        file_path = os.path.dirname(file_name)
        old_path = os.path.join(file_path, 'OLD')
        if not os.path.exists(old_path):
            os.mkdir(old_path)
        shutil.move(file_name, os.path.join(old_path, os.path.basename(file_name)))
