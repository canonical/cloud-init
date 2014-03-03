# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re

from Cheetah.Template import Template as CTemplate
from mako.template import Template as MTemplate

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)
DEF_RENDERER = (lambda content, params:
                CTemplate(content, searchList=[params]).respond())
RENDERERS = {
    'mako': lambda content, params: MTemplate(content).render(**params),
    'cheetah': DEF_RENDERER,
}
TYPE_MATCHER = re.compile(r"##\s*template:(.*)", re.I)


def detect_template(text):
    lines = text.splitlines()
    if not lines:
        return DEF_RENDERER
    line = lines[0]
    type_match = TYPE_MATCHER.match(line)
    if not type_match:
        return DEF_RENDERER
    template_type = type_match.group(1).lower().strip()
    if template_type not in RENDERERS:
        LOG.warn("Unknown template type requested: %s", template_type)
    return RENDERERS.get(template_type, DEF_RENDERER)


def render_from_file(fn, params):
    return render_string(util.load_file(fn), params)


def render_to_file(fn, outfn, params, mode=0644):
    contents = render_from_file(fn, params)
    util.write_file(outfn, contents, mode=mode)


def render_string(content, params):
    if not params:
        params = {}
    renderer = detect_template(content)
    return renderer(content, params)
