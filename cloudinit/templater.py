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

# noqa: E402

import collections
import logging
import re
import sys
import traceback
from typing import Any

from cloudinit import type_utils as tu
from cloudinit import util
from cloudinit.atomic_helper import write_file

# After bionic EOL, mypy==1.0.0 will be able to type-analyse dynamic
# base types, substitute this by:
# JUndefined: typing.Type
JUndefined: Any
try:
    from jinja2 import BaseLoader
    from jinja2 import DebugUndefined as _DebugUndefined
    from jinja2 import Environment
    from jinja2 import Template as JTemplate

    JINJA_AVAILABLE = True
    JUndefined = _DebugUndefined
except (ImportError, AttributeError):
    JINJA_AVAILABLE = False
    JUndefined = object

LOG = logging.getLogger(__name__)
TYPE_MATCHER = re.compile(r"##\s*template:(.*)", re.I)
BASIC_MATCHER = re.compile(r"\$\{([A-Za-z0-9_.]+)\}|\$([A-Za-z0-9_.]+)")
MISSING_JINJA_PREFIX = "CI_MISSING_JINJA_VAR/"


class CustomParsedJinjaException(Exception):
    pass


# Mypy, and the PEP 484 ecosystem in general, does not support creating
# classes with dynamic base types: https://stackoverflow.com/a/59636248
class UndefinedJinjaVariable(JUndefined):
    """Class used to represent any undefined jinja template variable."""

    def __str__(self):
        return "%s%s" % (MISSING_JINJA_PREFIX, self._undefined_name)

    def __sub__(self, other):
        other = str(other).replace(MISSING_JINJA_PREFIX, "")
        raise TypeError(
            'Undefined jinja variable: "{this}-{other}". Jinja tried'
            ' subtraction. Perhaps you meant "{this}_{other}"?'.format(
                this=self._undefined_name, other=other
            )
        )


def basic_render(content, params):
    """This does simple replacement of bash variable like templates.

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
                raise TypeError(
                    "Can not traverse into"
                    " non-dictionary '%s' of type %s while"
                    " looking for subkey '%s'"
                    % (selected_params, tu.obj_name(selected_params), key)
                )
            selected_params = selected_params[key]
        key = path.popleft()
        if not isinstance(selected_params, dict):
            raise TypeError(
                "Can not extract key '%s' from non-dictionary '%s' of type %s"
                % (key, selected_params, tu.obj_name(selected_params))
            )
        return str(selected_params[key])

    return BASIC_MATCHER.sub(replacer, content)


def detect_template(text):
    def jinja_render(content, params):
        # keep_trailing_newline is in jinja2 2.7+, not 2.6
        add = "\n" if content.endswith("\n") else ""
        try:
            result = JTemplate(
                content,
                undefined=UndefinedJinjaVariable,
                trim_blocks=True,
                extensions=["jinja2.ext.do"],
            ).render(**params) + add
            return result

        except Exception as JTemplateError:
            # print(JTemplateError)
            try:  # we know this next line will fail, but we want to get the traceback and error message it throws
                jinja_env = Environment(
                    loader=BaseLoader(),
                    autoescape=False,
                    undefined=UndefinedJinjaVariable,
                    trim_blocks=True,
                    extensions=["jinja2.ext.do"],
                )
                template = jinja_env.parse(content)
                # print("couldn't generate my own error message so re-raising JTEmplateError")
                raise JTemplateError
            # TODO: check other exception types
            except Exception as useful_jinja_error:
                try:
                    tb = "".join(
                        traceback.format_tb(useful_jinja_error.__traceback__)
                    )
                    # how reliable and robust is this across different OSs and versions
                    line_number_matches = re.findall(
                        r'File "<unknown>", line (\d+)', tb
                    )
                    line_number_of_error = int(line_number_matches[0])
                except:
                    raise JTemplateError
                # adjust line number for the fact that the jinja header has been removed from the content
                if content.split("\n")[0] == "#cloud-config":
                    line_number_of_error += 1
                raise CustomParsedJinjaException(
                    "{e} on line {line_no}".format(
                        e=useful_jinja_error,
                        line_no=line_number_of_error,
                    )
                )  # from None
        return result

    if text.find("\n") != -1:
        ident, rest = text.split("\n", 1)
    else:
        ident = text
        rest = ""
    type_match = TYPE_MATCHER.match(ident)
    if not type_match:
        return ("basic", basic_render, text)
    else:
        template_type = type_match.group(1).lower().strip()
        if template_type not in ("jinja", "basic"):
            raise ValueError(
                "Unknown template rendering type '%s' requested"
                % template_type
            )
        if template_type == "jinja" and not JINJA_AVAILABLE:
            LOG.warning(
                "Jinja not available as the selected renderer for"
                " desired template, reverting to the basic renderer."
            )
            return ("basic", basic_render, rest)
        elif template_type == "jinja" and JINJA_AVAILABLE:
            return ("jinja", jinja_render, rest)
        # Only thing left over is the basic renderer (it is always available).
        return ("basic", basic_render, rest)


def render_from_file(fn, params):
    if not params:
        params = {}
    template_type, renderer, content = detect_template(util.load_file(fn))
    LOG.debug("Rendering content of '%s' using renderer %s", fn, template_type)
    return renderer(content, params)


def render_to_file(fn, outfn, params, mode=0o644):
    contents = render_from_file(fn, params)
    util.write_file(outfn, contents, mode=mode)


def render_string(content, params):
    """Render string"""
    if not params:
        params = {}
    _template_type, renderer, content = detect_template(content)
    return renderer(content, params)


def render_cloudcfg(variant, template, output, prefix=None):
    with open(template, "r") as fh:
        contents = fh.read()
    tpl_params = {"variant": variant, "prefix": prefix}
    contents = (render_string(contents, tpl_params)).rstrip() + "\n"
    util.load_yaml(contents)
    if output == "-":
        sys.stdout.write(contents)
    else:
        write_file(output, contents, omode="w")
