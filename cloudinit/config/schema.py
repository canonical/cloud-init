# This file is part of cloud-init. See LICENSE file for license information.
"""schema.py: Set of module functions for processing cloud-config schema."""

from __future__ import print_function

from cloudinit import importer
from cloudinit.util import find_modules, load_file

import argparse
from collections import defaultdict
from copy import deepcopy
import logging
import os
import re
import sys
import yaml

_YAML_MAP = {True: 'true', False: 'false', None: 'null'}
SCHEMA_UNDEFINED = b'UNDEFINED'
CLOUD_CONFIG_HEADER = b'#cloud-config'
SCHEMA_DOC_TMPL = """
{name}
{title_underbar}
**Summary:** {title}

{description}

**Internal name:** ``{id}``

**Module frequency:** {frequency}

**Supported distros:** {distros}

**Config schema**:
{property_doc}
{examples}
"""
SCHEMA_PROPERTY_TMPL = '{prefix}**{prop_name}:** ({type}) {description}'
SCHEMA_EXAMPLES_HEADER = '\n**Examples**::\n\n'
SCHEMA_EXAMPLES_SPACER_TEMPLATE = '\n    # --- Example{0} ---'


class SchemaValidationError(ValueError):
    """Raised when validating a cloud-config file against a schema."""

    def __init__(self, schema_errors=()):
        """Init the exception an n-tuple of schema errors.

        @param schema_errors: An n-tuple of the format:
            ((flat.config.key, msg),)
        """
        self.schema_errors = schema_errors
        error_messages = [
            '{0}: {1}'.format(config_key, message)
            for config_key, message in schema_errors]
        message = "Cloud config schema errors: {0}".format(
            ', '.join(error_messages))
        super(SchemaValidationError, self).__init__(message)


def validate_cloudconfig_schema(config, schema, strict=False):
    """Validate provided config meets the schema definition.

    @param config: Dict of cloud configuration settings validated against
        schema.
    @param schema: jsonschema dict describing the supported schema definition
       for the cloud config module (config.cc_*).
    @param strict: Boolean, when True raise SchemaValidationErrors instead of
       logging warnings.

    @raises: SchemaValidationError when provided config does not validate
        against the provided schema.
    """
    try:
        from jsonschema import Draft4Validator, FormatChecker
    except ImportError:
        logging.debug(
            'Ignoring schema validation. python-jsonschema is not present')
        return
    validator = Draft4Validator(schema, format_checker=FormatChecker())
    errors = ()
    for error in sorted(validator.iter_errors(config), key=lambda e: e.path):
        path = '.'.join([str(p) for p in error.path])
        errors += ((path, error.message),)
    if errors:
        if strict:
            raise SchemaValidationError(errors)
        else:
            messages = ['{0}: {1}'.format(k, msg) for k, msg in errors]
            logging.warning('Invalid config:\n%s', '\n'.join(messages))


def annotated_cloudconfig_file(cloudconfig, original_content, schema_errors):
    """Return contents of the cloud-config file annotated with schema errors.

    @param cloudconfig: YAML-loaded dict from the original_content or empty
        dict if unparseable.
    @param original_content: The contents of a cloud-config file
    @param schema_errors: List of tuples from a JSONSchemaValidationError. The
        tuples consist of (schemapath, error_message).
    """
    if not schema_errors:
        return original_content
    schemapaths = {}
    if cloudconfig:
        schemapaths = _schemapath_for_cloudconfig(
            cloudconfig, original_content)
    errors_by_line = defaultdict(list)
    error_count = 1
    error_footer = []
    annotated_content = []
    for path, msg in schema_errors:
        match = re.match(r'format-l(?P<line>\d+)\.c(?P<col>\d+).*', path)
        if match:
            line, col = match.groups()
            errors_by_line[int(line)].append(msg)
        else:
            col = None
            errors_by_line[schemapaths[path]].append(msg)
        if col is not None:
            msg = 'Line {line} column {col}: {msg}'.format(
                line=line, col=col, msg=msg)
        error_footer.append('# E{0}: {1}'.format(error_count, msg))
        error_count += 1
    lines = original_content.decode().split('\n')
    error_count = 1
    for line_number, line in enumerate(lines):
        errors = errors_by_line[line_number + 1]
        if errors:
            error_label = ','.join(
                ['E{0}'.format(count + error_count)
                 for count in range(0, len(errors))])
            error_count += len(errors)
            annotated_content.append(line + '\t\t# ' + error_label)
        else:
            annotated_content.append(line)
    annotated_content.append(
        '# Errors: -------------\n{0}\n\n'.format('\n'.join(error_footer)))
    return '\n'.join(annotated_content)


def validate_cloudconfig_file(config_path, schema, annotate=False):
    """Validate cloudconfig file adheres to a specific jsonschema.

    @param config_path: Path to the yaml cloud-config file to parse.
    @param schema: Dict describing a valid jsonschema to validate against.
    @param annotate: Boolean set True to print original config file with error
        annotations on the offending lines.

    @raises SchemaValidationError containing any of schema_errors encountered.
    @raises RuntimeError when config_path does not exist.
    """
    if not os.path.exists(config_path):
        raise RuntimeError('Configfile {0} does not exist'.format(config_path))
    content = load_file(config_path, decode=False)
    if not content.startswith(CLOUD_CONFIG_HEADER):
        errors = (
            ('format-l1.c1', 'File {0} needs to begin with "{1}"'.format(
                config_path, CLOUD_CONFIG_HEADER.decode())),)
        error = SchemaValidationError(errors)
        if annotate:
            print(annotated_cloudconfig_file({}, content, error.schema_errors))
        raise error
    try:
        cloudconfig = yaml.safe_load(content)
    except (yaml.YAMLError) as e:
        line = column = 1
        mark = None
        if hasattr(e, 'context_mark') and getattr(e, 'context_mark'):
            mark = getattr(e, 'context_mark')
        elif hasattr(e, 'problem_mark') and getattr(e, 'problem_mark'):
            mark = getattr(e, 'problem_mark')
        if mark:
            line = mark.line + 1
            column = mark.column + 1
        errors = (('format-l{line}.c{col}'.format(line=line, col=column),
                   'File {0} is not valid yaml. {1}'.format(
                       config_path, str(e))),)
        error = SchemaValidationError(errors)
        if annotate:
            print(annotated_cloudconfig_file({}, content, error.schema_errors))
        raise error
    try:
        validate_cloudconfig_schema(
            cloudconfig, schema, strict=True)
    except SchemaValidationError as e:
        if annotate:
            print(annotated_cloudconfig_file(
                cloudconfig, content, e.schema_errors))
        raise


def _schemapath_for_cloudconfig(config, original_content):
    """Return a dictionary mapping schemapath to original_content line number.

    @param config: The yaml.loaded config dictionary of a cloud-config file.
    @param original_content: The simple file content of the cloud-config file
    """
    # FIXME Doesn't handle multi-line lists or multi-line strings
    content_lines = original_content.decode().split('\n')
    schema_line_numbers = {}
    list_index = 0
    RE_YAML_INDENT = r'^(\s*)'
    scopes = []
    for line_number, line in enumerate(content_lines, 1):
        indent_depth = len(re.match(RE_YAML_INDENT, line).groups()[0])
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if scopes:
            previous_depth, path_prefix = scopes[-1]
        else:
            previous_depth = -1
            path_prefix = ''
        if line.startswith('- '):
            key = str(list_index)
            value = line[1:]
            list_index += 1
        else:
            list_index = 0
            key, value = line.split(':', 1)
        while indent_depth <= previous_depth:
            if scopes:
                previous_depth, path_prefix = scopes.pop()
            else:
                previous_depth = -1
                path_prefix = ''
        if path_prefix:
            key = path_prefix + '.' + key
        scopes.append((indent_depth, key))
        if value:
            value = value.strip()
            if value.startswith('['):
                scopes.append((indent_depth + 2, key + '.0'))
                for inner_list_index in range(0, len(yaml.safe_load(value))):
                    list_key = key + '.' + str(inner_list_index)
                    schema_line_numbers[list_key] = line_number
        schema_line_numbers[key] = line_number
    return schema_line_numbers


def _get_property_type(property_dict):
    """Return a string representing a property type from a given jsonschema."""
    property_type = property_dict.get('type', SCHEMA_UNDEFINED)
    if property_type == SCHEMA_UNDEFINED and property_dict.get('enum'):
        property_type = [
            str(_YAML_MAP.get(k, k)) for k in property_dict['enum']]
    if isinstance(property_type, list):
        property_type = '/'.join(property_type)
    items = property_dict.get('items', {})
    sub_property_type = items.get('type', '')
    # Collect each item type
    for sub_item in items.get('oneOf', {}):
        if sub_property_type:
            sub_property_type += '/'
        sub_property_type += '(' + _get_property_type(sub_item) + ')'
    if sub_property_type:
        return '{0} of {1}'.format(property_type, sub_property_type)
    return property_type


def _get_property_doc(schema, prefix='    '):
    """Return restructured text describing the supported schema properties."""
    new_prefix = prefix + '    '
    properties = []
    for prop_key, prop_config in schema.get('properties', {}).items():
        # Define prop_name and dscription for SCHEMA_PROPERTY_TMPL
        description = prop_config.get('description', '')
        properties.append(SCHEMA_PROPERTY_TMPL.format(
            prefix=prefix,
            prop_name=prop_key,
            type=_get_property_type(prop_config),
            description=description.replace('\n', '')))
        if 'properties' in prop_config:
            properties.append(
                _get_property_doc(prop_config, prefix=new_prefix))
    return '\n\n'.join(properties)


def _get_schema_examples(schema, prefix=''):
    """Return restructured text describing the schema examples if present."""
    examples = schema.get('examples')
    if not examples:
        return ''
    rst_content = SCHEMA_EXAMPLES_HEADER
    for count, example in enumerate(examples):
        # Python2.6 is missing textwrapper.indent
        lines = example.split('\n')
        indented_lines = ['    {0}'.format(line) for line in lines]
        if rst_content != SCHEMA_EXAMPLES_HEADER:
            indented_lines.insert(
                0, SCHEMA_EXAMPLES_SPACER_TEMPLATE.format(count + 1))
        rst_content += '\n'.join(indented_lines)
    return rst_content


def get_schema_doc(schema):
    """Return reStructured text rendering the provided jsonschema.

    @param schema: Dict of jsonschema to render.
    @raise KeyError: If schema lacks an expected key.
    """
    schema_copy = deepcopy(schema)
    schema_copy['property_doc'] = _get_property_doc(schema)
    schema_copy['examples'] = _get_schema_examples(schema)
    schema_copy['distros'] = ', '.join(schema['distros'])
    # Need an underbar of the same length as the name
    schema_copy['title_underbar'] = re.sub(r'.', '-', schema['name'])
    return SCHEMA_DOC_TMPL.format(**schema_copy)


FULL_SCHEMA = None


def get_schema():
    """Return jsonschema coalesced from all cc_* cloud-config module."""
    global FULL_SCHEMA
    if FULL_SCHEMA:
        return FULL_SCHEMA
    full_schema = {
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'id': 'cloud-config-schema', 'allOf': []}

    configs_dir = os.path.dirname(os.path.abspath(__file__))
    potential_handlers = find_modules(configs_dir)
    for (_fname, mod_name) in potential_handlers.items():
        mod_locs, _looked_locs = importer.find_module(
            mod_name, ['cloudinit.config'], ['schema'])
        if mod_locs:
            mod = importer.import_module(mod_locs[0])
            full_schema['allOf'].append(mod.schema)
    FULL_SCHEMA = full_schema
    return full_schema


def error(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def get_parser(parser=None):
    """Return a parser for supported cmdline arguments."""
    if not parser:
        parser = argparse.ArgumentParser(
            prog='cloudconfig-schema',
            description='Validate cloud-config files or document schema')
    parser.add_argument('-c', '--config-file',
                        help='Path of the cloud-config yaml file to validate')
    parser.add_argument('-d', '--doc', action="store_true", default=False,
                        help='Print schema documentation')
    parser.add_argument('--annotate', action="store_true", default=False,
                        help='Annotate existing cloud-config file with errors')
    return parser


def handle_schema_args(name, args):
    """Handle provided schema args and perform the appropriate actions."""
    exclusive_args = [args.config_file, args.doc]
    if not any(exclusive_args) or all(exclusive_args):
        error('Expected either --config-file argument or --doc')
    full_schema = get_schema()
    if args.config_file:
        try:
            validate_cloudconfig_file(
                args.config_file, full_schema, args.annotate)
        except SchemaValidationError as e:
            if not args.annotate:
                error(str(e))
        except RuntimeError as e:
                error(str(e))
        else:
            print("Valid cloud-config file {0}".format(args.config_file))
    if args.doc:
        for subschema in full_schema['allOf']:
            print(get_schema_doc(subschema))


def main():
    """Tool to validate schema of a cloud-config file or print schema docs."""
    parser = get_parser()
    handle_schema_args('cloudconfig-schema', parser.parse_args())
    return 0


if __name__ == '__main__':
    sys.exit(main())

# vi: ts=4 expandtab
