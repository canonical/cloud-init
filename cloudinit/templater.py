# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2016 Amazon.com, Inc. or its affiliates.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Andrew Jorgensen <ajorgens@amazon.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import collections
import re


try:
    from Cheetah.Template import Template as CTemplate
    CHEETAH_AVAILABLE = True
except (ImportError, AttributeError):
    CHEETAH_AVAILABLE = False

try:
    from jinja2.runtime import implements_to_string
    from jinja2 import Template as JTemplate
    from jinja2 import DebugUndefined as JUndefined
    JINJA_AVAILABLE = True
except (ImportError, AttributeError):
    from cloudinit.helpers import identity
    implements_to_string = identity
    JINJA_AVAILABLE = False
    JUndefined = object

from cloudinit import log as logging
from cloudinit import type_utils as tu
from cloudinit import util


LOG = logging.getLogger(__name__)
TYPE_MATCHER = re.compile(r"##\s*template:(.*)", re.I)
BASIC_MATCHER = re.compile(r'\$\{([A-Za-z0-9_.]+)\}|\$([A-Za-z0-9_.]+)')
MISSING_JINJA_PREFIX = u'CI_MISSING_JINJA_VAR/'


@implements_to_string   # Needed for python2.7. Otherwise cached super.__str__
class UndefinedJinjaVariable(JUndefined):
    """Class used to represent any undefined jinja template varible."""

    def __str__(self):
        return u'%s%s' % (MISSING_JINJA_PREFIX, self._undefined_name)

    def __sub__(self, other):
        other = str(other).replace(MISSING_JINJA_PREFIX, '')
        raise TypeError(
            'Undefined jinja variable: "{this}-{other}". Jinja tried'
            ' subtraction. Perhaps you meant "{this}_{other}"?'.format(
                this=self._undefined_name, other=other))


def basic_render(content, params):
    """This does sumple replacement of bash variable like templates.

    It identifies patterns like ${a} or $a and can also identify patterns like
    ${a.b} or $a.b which will look for a key 'b' in the dictionary rooted
    by key 'a'.
    """

    def replacer(match):
        # Only 1 of the 2 groups will actually have a valid entry.
        name = match.group(1)
        if name is None:
            name = match.group(2)
        if name is None:
            raise RuntimeError("Match encountered but no valid group present")
        path = collections.deque(name.split("."))
        selected_params = params
        while len(path) > 1:
            key = path.popleft()
            if not isinstance(selected_params, dict):
                raise TypeError("Can not traverse into"
                                " non-dictionary '%s' of type %s while"
                                " looking for subkey '%s'"
                                % (selected_params,
                                   tu.obj_name(selected_params),
                                   key))
            selected_params = selected_params[key]
        key = path.popleft()
        if not isinstance(selected_params, dict):
            raise TypeError("Can not extract key '%s' from non-dictionary"
                            " '%s' of type %s"
                            % (key, selected_params,
                               tu.obj_name(selected_params)))
        return str(selected_params[key])

    return BASIC_MATCHER.sub(replacer, content)


def detect_template(text):

    def cheetah_render(content, params):
        return CTemplate(content, searchList=[params]).respond()

    def jinja_render(content, params):
        # keep_trailing_newline is in jinja2 2.7+, not 2.6
        add = "\n" if content.endswith("\n") else ""
        return JTemplate(content,
                         undefined=UndefinedJinjaVariable,
                         trim_blocks=True).render(**params) + add

    if text.find("\n") != -1:
        ident, rest = text.split("\n", 1)
    else:
        ident = text
        rest = ''
    type_match = TYPE_MATCHER.match(ident)
    if not type_match:
        if CHEETAH_AVAILABLE:
            LOG.debug("Using Cheetah as the renderer for unknown template.")
            return ('cheetah', cheetah_render, text)
        else:
            return ('basic', basic_render, text)
    else:
        template_type = type_match.group(1).lower().strip()
        if template_type not in ('jinja', 'cheetah', 'basic'):
            raise ValueError("Unknown template rendering type '%s' requested"
                             % template_type)
        if template_type == 'jinja' and not JINJA_AVAILABLE:
            LOG.warning("Jinja not available as the selected renderer for"
                        " desired template, reverting to the basic renderer.")
            return ('basic', basic_render, rest)
        elif template_type == 'jinja' and JINJA_AVAILABLE:
            return ('jinja', jinja_render, rest)
        if template_type == 'cheetah' and not CHEETAH_AVAILABLE:
            LOG.warning("Cheetah not available as the selected renderer for"
                        " desired template, reverting to the basic renderer.")
            return ('basic', basic_render, rest)
        elif template_type == 'cheetah' and CHEETAH_AVAILABLE:
            return ('cheetah', cheetah_render, rest)
        # Only thing left over is the basic renderer (it is always available).
        return ('basic', basic_render, rest)


def render_from_file(fn, params):
    if not params:
        params = {}
    # jinja in python2 uses unicode internally.  All py2 str will be decoded.
    # If it is given a str that has non-ascii then it will raise a
    # UnicodeDecodeError.  So we explicitly convert to unicode type here.
    template_type, renderer, content = detect_template(
        util.load_file(fn, decode=False).decode('utf-8'))
    LOG.debug("Rendering content of '%s' using renderer %s", fn, template_type)
    return renderer(content, params)


def render_to_file(fn, outfn, params, mode=0o644):
    contents = render_from_file(fn, params)
    util.write_file(outfn, contents, mode=mode)


def render_string_to_file(content, outfn, params, mode=0o644):
    """Render string (or py2 unicode) to file.
    Warning: py2 str with non-ascii chars will cause UnicodeDecodeError."""
    contents = render_string(content, params)
    util.write_file(outfn, contents, mode=mode)


def render_string(content, params):
    """Render string (or py2 unicode).
    Warning: py2 str with non-ascii chars will cause UnicodeDecodeError."""
    if not params:
        params = {}
    _template_type, renderer, content = detect_template(content)
    return renderer(content, params)

# vi: ts=4 expandtab
