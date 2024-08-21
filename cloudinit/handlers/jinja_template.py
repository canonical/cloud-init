# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
import os
import re
from errno import EACCES
from typing import Optional, Type

from cloudinit import handlers
from cloudinit.atomic_helper import b64d, json_dumps
from cloudinit.helpers import Paths
from cloudinit.settings import PER_ALWAYS
from cloudinit.templater import (
    MISSING_JINJA_PREFIX,
    JinjaSyntaxParsingException,
    detect_template,
    render_string,
)
from cloudinit.util import load_json, load_text_file

JUndefinedError: Type[Exception]
try:
    from jinja2.exceptions import UndefinedError as JUndefinedError
    from jinja2.lexer import operator_re
except ImportError:
    # No jinja2 dependency
    JUndefinedError = Exception
    operator_re = re.compile(r"[-.]")

LOG = logging.getLogger(__name__)


class JinjaLoadError(Exception):
    pass


class NotJinjaError(Exception):
    pass


class JinjaTemplatePartHandler(handlers.Handler):

    prefixes = ["## template: jinja"]

    def __init__(self, paths: Paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS, version=3)
        self.paths = paths
        self.sub_handlers = {}
        for handler in _kwargs.get("sub_handlers", []):
            for ctype in handler.list_types():
                self.sub_handlers[ctype] = handler

    def handle_part(self, data, ctype, filename, payload, frequency, headers):
        if ctype in handlers.CONTENT_SIGNALS:
            return
        jinja_json_file = self.paths.get_runpath("instance_data_sensitive")
        try:
            rendered_payload = render_jinja_payload_from_file(
                payload, filename, jinja_json_file
            )
        except JinjaSyntaxParsingException as e:
            LOG.warning(
                "Ignoring jinja template for %s. "
                "Failed to render template. %s",
                filename,
                str(e),
            )
            return

        if not rendered_payload:
            return
        subtype = handlers.type_from_starts_with(rendered_payload)
        sub_handler = self.sub_handlers.get(subtype)
        if not sub_handler:
            LOG.warning(
                "Ignoring jinja template for %s. Could not find supported"
                " sub-handler for type %s",
                filename,
                subtype,
            )
            return
        if sub_handler.handler_version == 3:
            sub_handler.handle_part(
                data, ctype, filename, rendered_payload, frequency, headers
            )
        elif sub_handler.handler_version == 2:
            sub_handler.handle_part(
                data, ctype, filename, rendered_payload, frequency
            )


def render_jinja_payload_from_file(
    payload, payload_fn, instance_data_file, debug=False
):
    r"""Render a jinja template sourcing variables from jinja_vars_path.

    @param payload: String of jinja template content. Should begin with
        ## template: jinja\n.
    @param payload_fn: String representing the filename from which the payload
        was read used in error reporting. Generally in part-handling this is
        'part-##'.
    @param instance_data_file: A path to a json file containing variables that
        will be used as jinja template variables.

    @return: A string of jinja-rendered content with the jinja header removed.
        Returns None on error.
    """
    if detect_template(payload)[0] != "jinja":
        raise NotJinjaError("Payload is not a jinja template")
    instance_data = {}
    rendered_payload = None
    if not os.path.exists(instance_data_file):
        raise JinjaLoadError(
            "Cannot render jinja template vars. Instance data not yet"
            " present at %s" % instance_data_file
        )
    try:
        instance_data = load_json(load_text_file(instance_data_file))
    except Exception as e:
        msg = "Loading Jinja instance data failed"
        if isinstance(e, (IOError, OSError)):
            if e.errno == EACCES:
                msg = (
                    "Cannot render jinja template vars. No read permission on"
                    " '%s'. Try sudo" % instance_data_file
                )
        raise JinjaLoadError(msg) from e

    rendered_payload = render_jinja_payload(
        payload, payload_fn, instance_data, debug
    )
    if not rendered_payload:
        return None
    return rendered_payload


def render_jinja_payload(payload, payload_fn, instance_data, debug=False):
    instance_jinja_vars = convert_jinja_instance_data(
        instance_data,
        decode_paths=instance_data.get("base64-encoded-keys", []),
        include_key_aliases=True,
    )
    if debug:
        LOG.debug(
            "Converted jinja variables\n%s", json_dumps(instance_jinja_vars)
        )
    try:
        rendered_payload = render_string(payload, instance_jinja_vars)
    except (TypeError, JUndefinedError) as e:
        LOG.warning("Ignoring jinja template for %s: %s", payload_fn, str(e))
        return None
    warnings = [
        "'%s'" % var.replace(MISSING_JINJA_PREFIX, "")
        for var in re.findall(
            r"%s[^\s]+" % MISSING_JINJA_PREFIX, rendered_payload
        )
    ]
    if warnings:
        LOG.warning(
            "Could not render jinja template variables in file '%s': %s",
            payload_fn,
            ", ".join(warnings),
        )
    return rendered_payload


def get_jinja_variable_alias(orig_name: str) -> Optional[str]:
    """Return a jinja variable alias, replacing any operators with underscores.

    Provide underscore-delimited key aliases to simplify dot-notation
    attribute references for keys which contain operators "." or "-".
    This provides for simpler short-hand jinja attribute notation
    allowing one to avoid quoting keys which contain operators.
    {{ ds.v1_0.config.user_network_config }} instead of
    {{ ds['v1.0'].config["user.network-config"] }}.

    :param orig_name: String representing a jinja variable name to scrub/alias.

    :return: A string with any jinja operators replaced if needed. Otherwise,
        none if no alias required.
    """
    alias_name = re.sub(operator_re, "_", orig_name)
    if alias_name != orig_name:
        return alias_name
    return None


def convert_jinja_instance_data(
    data, prefix="", sep="/", decode_paths=(), include_key_aliases=False
):
    """Process instance-data.json dict for use in jinja templates.

    Replace hyphens with underscores for jinja templates and decode any
    base64_encoded_keys.
    """
    result = {}
    decode_paths = [path.replace("-", "_") for path in decode_paths]
    for key, value in sorted(data.items()):
        key_path = "{0}{1}{2}".format(prefix, sep, key) if prefix else key
        if key_path in decode_paths:
            value = b64d(value)
        if isinstance(value, dict):
            result[key] = convert_jinja_instance_data(
                value,
                key_path,
                sep=sep,
                decode_paths=decode_paths,
                include_key_aliases=include_key_aliases,
            )
            if re.match(r"v\d+$", key):
                # Copy values to top-level aliases
                for subkey, subvalue in result[key].items():
                    result[subkey] = copy.deepcopy(subvalue)
        else:
            result[key] = value
        if include_key_aliases:
            alias_name = get_jinja_variable_alias(key)
            if alias_name:
                result[alias_name] = copy.deepcopy(result[key])
    return result
