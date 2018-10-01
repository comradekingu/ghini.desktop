# -*- coding: utf-8 -*-
#
# Copyright 2008-2010 Brett Adams
# Copyright 2012-2016 Mario Frasca <mario@anche.no>.
# Copyright 2017 Jardín Botánico de Quito
#
# This file is part of ghini.desktop.
#
# ghini.desktop is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ghini.desktop is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ghini.desktop. If not, see <http://www.gnu.org/licenses/>.
#
# report/mako/
#

import logging
logger = logging.getLogger(__name__)

import re

from gi.repository import Gtk

from bauble.plugins.report import TemplateFormatterPlugin
import bauble.utils as utils


class MakoFormatterPlugin(TemplateFormatterPlugin):
    """
    The MakoFormatterPlugin passes the values in the search
    results directly to a Mako template.  It is up to the template
    author to validate the type of the values and act accordingly if not.
    """

    title = 'Mako'
    extension = '.mako'
    domain_pattern = re.compile(r"^##\s*DOMAIN\s+([a-z_]*)\s*$")
    option_pattern = re.compile("^## OPTION ([a-z_]*): \("
                                "type: ([a-z_]*), "
                                "default: '(.*)', "
                                "tooltip: '(.*)'\)$")

    @classmethod
    def get_template(cls, template_filename):
        if not template_filename:
            msg = _('Please select a template.')
            utils.idle_message(msg, Gtk.MessageType.WARNING)
            return False
        try:
            from mako.template import Template
            template = Template(filename=template_filename,
                                input_encoding='utf-8', output_encoding='utf-8')
        except RuntimeError as e:
            import traceback
            utils.idle_message("Reading template %s\n%s(%s)\n%s" % (template_filename, type(e).__name__, e, traceback.format_exc()), type=Gtk.MessageType.ERROR)
            return False

        return template


formatter_plugin = MakoFormatterPlugin
