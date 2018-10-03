# This file is part of cloud-init. See LICENSE file for license information.

import os
import re

try:
    from jinja2.exceptions import UndefinedError as JUndefinedError
except ImportError:
    # No jinja2 dependency
    JUndefinedError = Exception

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit.sources import INSTANCE_JSON_FILE
from cloudinit.templater import render_string, MISSING_JINJA_PREFIX
from cloudinit.util import b64d, load_file, load_json, json_dumps

from cloudinit.settings import PER_ALWAYS

LOG = logging.getLogger(__name__)


class JinjaTemplatePartHandler(handlers.Handler):

    prefixes = ['## template: jinja']

    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS, version=3)
        self.paths = paths
        self.sub_handlers = {}
        for handler in _kwargs.get('sub_handlers', []):
            for ctype in handler.list_types():
                self.sub_handlers[ctype] = handler

    def handle_part(self, data, ctype, filename, payload, frequency, headers):
        if ctype in handlers.CONTENT_SIGNALS:
            return
        jinja_json_file = os.path.join(self.paths.run_dir, INSTANCE_JSON_FILE)
        rendered_payload = render_jinja_payload_from_file(
            payload, filename, jinja_json_file)
        if not rendered_payload:
            return
        subtype = handlers.type_from_starts_with(rendered_payload)
        sub_handler = self.sub_handlers.get(subtype)
        if not sub_handler:
            LOG.warning(
                'Ignoring jinja template for %s. Could not find supported'
                ' sub-handler for type %s', filename, subtype)
            return
        if sub_handler.handler_version == 3:
            sub_handler.handle_part(
                data, ctype, filename, rendered_payload, frequency, headers)
        elif sub_handler.handler_version == 2:
            sub_handler.handle_part(
                data, ctype, filename, rendered_payload, frequency)


def render_jinja_payload_from_file(
        payload, payload_fn, instance_data_file, debug=False):
    """Render a jinja template payload sourcing variables from jinja_vars_path.

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
    instance_data = {}
    rendered_payload = None
    if not os.path.exists(instance_data_file):
        raise RuntimeError(
            'Cannot render jinja template vars. Instance data not yet'
            ' present at %s' % instance_data_file)
    instance_data = load_json(load_file(instance_data_file))
    rendered_payload = render_jinja_payload(
        payload, payload_fn, instance_data, debug)
    if not rendered_payload:
        return None
    return rendered_payload


def render_jinja_payload(payload, payload_fn, instance_data, debug=False):
    instance_jinja_vars = convert_jinja_instance_data(
        instance_data,
        decode_paths=instance_data.get('base64-encoded-keys', []))
    if debug:
        LOG.debug('Converted jinja variables\n%s',
                  json_dumps(instance_jinja_vars))
    try:
        rendered_payload = render_string(payload, instance_jinja_vars)
    except (TypeError, JUndefinedError) as e:
        LOG.warning(
            'Ignoring jinja template for %s: %s', payload_fn, str(e))
        return None
    warnings = [
        "'%s'" % var.replace(MISSING_JINJA_PREFIX, '')
        for var in re.findall(
            r'%s[^\s]+' % MISSING_JINJA_PREFIX, rendered_payload)]
    if warnings:
        LOG.warning(
            "Could not render jinja template variables in file '%s': %s",
            payload_fn, ', '.join(warnings))
    return rendered_payload


def convert_jinja_instance_data(data, prefix='', sep='/', decode_paths=()):
    """Process instance-data.json dict for use in jinja templates.

    Replace hyphens with underscores for jinja templates and decode any
    base64_encoded_keys.
    """
    result = {}
    decode_paths = [path.replace('-', '_') for path in decode_paths]
    for key, value in sorted(data.items()):
        if '-' in key:
            # Standardize keys for use in #cloud-config/shell templates
            key = key.replace('-', '_')
        key_path = '{0}{1}{2}'.format(prefix, sep, key) if prefix else key
        if key_path in decode_paths:
            value = b64d(value)
        if isinstance(value, dict):
            result[key] = convert_jinja_instance_data(
                value, key_path, sep=sep, decode_paths=decode_paths)
            if re.match(r'v\d+', key):
                # Copy values to top-level aliases
                for subkey, subvalue in result[key].items():
                    result[subkey] = subvalue
        else:
            result[key] = value
    return result

# vi: ts=4 expandtab
