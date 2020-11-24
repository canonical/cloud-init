# This file is part of cloud-init. See LICENSE file for license information.
"""schema.py: Set of module functions for processing cloud-config schema."""

from cloudinit.cmd.devel import read_cfg_paths
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
SCHEMA_LIST_ITEM_TMPL = (
    '{prefix}Each item in **{prop_name}** list supports the following keys:')
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


def is_schema_byte_string(checker, instance):
    """TYPE_CHECKER override allowing bytes for string type

    For jsonschema v. 3.0.0+
    """
    try:
        from jsonschema import Draft4Validator
    except ImportError:
        return False
    return (Draft4Validator.TYPE_CHECKER.is_type(instance, "string") or
            isinstance(instance, (bytes,)))


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
        from jsonschema.validators import create, extend
    except ImportError:
        logging.debug(
            'Ignoring schema validation. python-jsonschema is not present')
        return

    # Allow for bytes to be presented as an acceptable valid value for string
    # type jsonschema attributes in cloud-init's schema.
    # This allows #cloud-config to provide valid yaml "content: !!binary | ..."
    if hasattr(Draft4Validator, 'TYPE_CHECKER'):  # jsonschema 3.0+
        type_checker = Draft4Validator.TYPE_CHECKER.redefine(
            'string', is_schema_byte_string)
        cloudinitValidator = extend(Draft4Validator, type_checker=type_checker)
    else:  # jsonschema 2.6 workaround
        types = Draft4Validator.DEFAULT_TYPES
        # Allow bytes as well as string (and disable a spurious
        # unsupported-assignment-operation pylint warning which appears because
        # this code path isn't written against the latest jsonschema).
        types['string'] = (str, bytes)  # pylint: disable=E1137
        cloudinitValidator = create(
            meta_schema=Draft4Validator.META_SCHEMA,
            validators=Draft4Validator.VALIDATORS,
            version="draft4",
            default_types=types)
    validator = cloudinitValidator(schema, format_checker=FormatChecker())
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
    lines = original_content.decode().split('\n')
    error_index = 1
    for line_number, line in enumerate(lines, 1):
        errors = errors_by_line[line_number]
        if errors:
            error_label = []
            for error in errors:
                error_label.append('E{0}'.format(error_index))
                error_footer.append('# E{0}: {1}'.format(error_index, error))
                error_index += 1
            annotated_content.append(line + '\t\t# ' + ','.join(error_label))
        else:
            annotated_content.append(line)
    annotated_content.append(
        '# Errors: -------------\n{0}\n\n'.format('\n'.join(error_footer)))
    return '\n'.join(annotated_content)


def validate_cloudconfig_file(config_path, schema, annotate=False):
    """Validate cloudconfig file adheres to a specific jsonschema.

    @param config_path: Path to the yaml cloud-config file to parse, or None
        to default to system userdata from Paths object.
    @param schema: Dict describing a valid jsonschema to validate against.
    @param annotate: Boolean set True to print original config file with error
        annotations on the offending lines.

    @raises SchemaValidationError containing any of schema_errors encountered.
    @raises RuntimeError when config_path does not exist.
    """
    if config_path is None:
        # Use system's raw userdata path
        if os.getuid() != 0:
            raise RuntimeError(
                "Unable to read system userdata as non-root user."
                " Try using sudo"
            )
        paths = read_cfg_paths()
        user_data_file = paths.get_ipath_cur("userdata_raw")
        content = load_file(user_data_file, decode=False)
    else:
        if not os.path.exists(config_path):
            raise RuntimeError(
                'Configfile {0} does not exist'.format(
                    config_path
                )
            )
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
        raise error from e
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
            # Process list items adding a list_index to the path prefix
            previous_list_idx = '.%d' % (list_index - 1)
            if path_prefix and path_prefix.endswith(previous_list_idx):
                path_prefix = path_prefix[:-len(previous_list_idx)]
            key = str(list_index)
            schema_line_numbers[key] = line_number
            item_indent = len(re.match(RE_YAML_INDENT, line[1:]).groups()[0])
            item_indent += 1  # For the leading '-' character
            previous_depth = indent_depth
            indent_depth += item_indent
            line = line[item_indent:]  # Strip leading list item + whitespace
            list_index += 1
        else:
            # Process non-list lines setting value if present
            list_index = 0
            key, value = line.split(':', 1)
        if path_prefix:
            # Append any existing path_prefix for a fully-pathed key
            key = path_prefix + '.' + key
        while indent_depth <= previous_depth:
            if scopes:
                previous_depth, path_prefix = scopes.pop()
                if list_index > 0 and indent_depth == previous_depth:
                    path_prefix = '.'.join(path_prefix.split('.')[:-1])
                    break
            else:
                previous_depth = -1
                path_prefix = ''
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


def _parse_description(description, prefix):
    """Parse description from the schema in a format that we can better
    display in our docs. This parser does three things:

    - Guarantee that a paragraph will be in a single line
    - Guarantee that each new paragraph will be aligned with
      the first paragraph
    - Proper align lists of items

    @param description: The original description in the schema.
    @param prefix: The number of spaces used to align the current description
    """
    list_paragraph = prefix * 3
    description = re.sub(r"(\S)\n(\S)", r"\1 \2", description)
    description = re.sub(
        r"\n\n", r"\n\n{}".format(prefix), description)
    description = re.sub(
        r"\n( +)-", r"\n{}-".format(list_paragraph), description)

    return description


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
            description=_parse_description(description, prefix)))
        items = prop_config.get('items')
        if items:
            if isinstance(items, list):
                for item in items:
                    properties.append(
                        _get_property_doc(item, prefix=new_prefix))
            elif isinstance(items, dict) and items.get('properties'):
                properties.append(SCHEMA_LIST_ITEM_TMPL.format(
                    prefix=new_prefix, prop_name=prop_key))
                new_prefix += '    '
                properties.append(_get_property_doc(items, prefix=new_prefix))
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
    parser.add_argument('--system', action='store_true', default=False,
                        help='Validate the system cloud-config userdata')
    parser.add_argument('-d', '--docs', nargs='+',
                        help=('Print schema module docs. Choices: all or'
                              ' space-delimited cc_names.'))
    parser.add_argument('--annotate', action="store_true", default=False,
                        help='Annotate existing cloud-config file with errors')
    return parser


def handle_schema_args(name, args):
    """Handle provided schema args and perform the appropriate actions."""
    exclusive_args = [args.config_file, args.docs, args.system]
    if len([arg for arg in exclusive_args if arg]) != 1:
        error('Expected one of --config-file, --system or --docs arguments')
    full_schema = get_schema()
    if args.config_file or args.system:
        try:
            validate_cloudconfig_file(
                args.config_file, full_schema, args.annotate)
        except SchemaValidationError as e:
            if not args.annotate:
                error(str(e))
        except RuntimeError as e:
            error(str(e))
        else:
            if args.config_file is None:
                cfg_name = "system userdata"
            else:
                cfg_name = args.config_file
            print("Valid cloud-config:", cfg_name)
    elif args.docs:
        schema_ids = [subschema['id'] for subschema in full_schema['allOf']]
        schema_ids += ['all']
        invalid_docs = set(args.docs).difference(set(schema_ids))
        if invalid_docs:
            error('Invalid --docs value {0}. Must be one of: {1}'.format(
                  list(invalid_docs), ', '.join(schema_ids)))
        for subschema in full_schema['allOf']:
            if 'all' in args.docs or subschema['id'] in args.docs:
                print(get_schema_doc(subschema))


def main():
    """Tool to validate schema of a cloud-config file or print schema docs."""
    parser = get_parser()
    handle_schema_args('cloudconfig-schema', parser.parse_args())
    return 0


if __name__ == '__main__':
    sys.exit(main())

# vi: ts=4 expandtab
