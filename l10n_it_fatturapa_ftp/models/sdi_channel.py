# -*- coding: utf-8 -*-
##############################################################################
#
#    OmniaSolutions, ERP-PLM-CAD Open Source Solution
#    Copyright (C) 2011-2019 OmniaSolutions.eu
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this prograIf not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
'''
Created on Feb 16, 2019

@author: mboscolo
'''

from odoo import models
from odoo import fields
from odoo import api
from odoo import _
from odoo import exceptions


class SdiChannelFTP(models.Model):
    _inherit = "sdi.channel"
    channel_type = fields.Selection(selection_add=[('ftp', 'FTP')])

    folder_from_sdi = fields.Char(string='Folder From SDI')
    folder_to_sdi = fields.Char(string='Folder To SDI')
