# This file is part of cloud-init. See LICENSE file for license information.
"""schema.py: Set of module functions for processing cloud-config schema."""

from __future__ import print_function

from cloudinit.util import read_file_or_url

import argparse
import logging
import os
import sys
import yaml

SCHEMA_UNDEFINED = b'UNDEFINED'
CLOUD_CONFIG_HEADER = b'#cloud-config'
SCHEMA_DOC_TMPL = """
{name}
---
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
        logging.warning(
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


def validate_cloudconfig_file(config_path, schema):
    """Validate cloudconfig file adheres to a specific jsonschema.

    @param config_path: Path to the yaml cloud-config file to parse.
    @param schema: Dict describing a valid jsonschema to validate against.

    @raises SchemaValidationError containing any of schema_errors encountered.
    @raises RuntimeError when config_path does not exist.
    """
    if not os.path.exists(config_path):
        raise RuntimeError('Configfile {0} does not exist'.format(config_path))
    content = read_file_or_url('file://{0}'.format(config_path)).contents
    if not content.startswith(CLOUD_CONFIG_HEADER):
        errors = (
            ('header', 'File {0} needs to begin with "{1}"'.format(
                config_path, CLOUD_CONFIG_HEADER.decode())),)
        raise SchemaValidationError(errors)

    try:
        cloudconfig = yaml.safe_load(content)
    except yaml.parser.ParserError as e:
        errors = (
            ('format', 'File {0} is not valid yaml. {1}'.format(
                config_path, str(e))),)
        raise SchemaValidationError(errors)
    validate_cloudconfig_schema(
        cloudconfig, schema, strict=True)


def _get_property_type(property_dict):
    """Return a string representing a property type from a given jsonschema."""
    property_type = property_dict.get('type', SCHEMA_UNDEFINED)
    if isinstance(property_type, list):
        property_type = '/'.join(property_type)
    item_type = property_dict.get('items', {}).get('type')
    if item_type:
        property_type = '{0} of {1}'.format(property_type, item_type)
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
    rst_content = '\n**Examples**::\n\n'
    for example in examples:
        example_yaml = yaml.dump(example, default_flow_style=False)
        # Python2.6 is missing textwrapper.indent
        lines = example_yaml.split('\n')
        indented_lines = ['    {0}'.format(line) for line in lines]
        rst_content += '\n'.join(indented_lines)
    return rst_content


def get_schema_doc(schema):
    """Return reStructured text rendering the provided jsonschema.

    @param schema: Dict of jsonschema to render.
    @raise KeyError: If schema lacks an expected key.
    """
    schema['property_doc'] = _get_property_doc(schema)
    schema['examples'] = _get_schema_examples(schema)
    schema['distros'] = ', '.join(schema['distros'])
    return SCHEMA_DOC_TMPL.format(**schema)


def get_schema(section_key=None):
    """Return a dict of jsonschema defined in any cc_* module.

    @param: section_key: Optionally limit schema to a specific top-level key.
    """
    # TODO use util.find_modules in subsequent branch
    from cloudinit.config.cc_ntp import schema
    return schema


def error(message):
    print(message, file=sys.stderr)
    return 1


def get_parser():
    """Return a parser for supported cmdline arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config-file',
                        help='Path of the cloud-config yaml file to validate')
    parser.add_argument('-d', '--doc', action="store_true", default=False,
                        help='Print schema documentation')
    parser.add_argument('-k', '--key',
                        help='Limit validation or docs to a section key')
    return parser


def main():
    """Tool to validate schema of a cloud-config file or print schema docs."""
    parser = get_parser()
    args = parser.parse_args()
    exclusive_args = [args.config_file, args.doc]
    if not any(exclusive_args) or all(exclusive_args):
        return error('Expected either --config-file argument or --doc')

    schema = get_schema()
    if args.config_file:
        try:
            validate_cloudconfig_file(args.config_file, schema)
        except (SchemaValidationError, RuntimeError) as e:
            return error(str(e))
        print("Valid cloud-config file {0}".format(args.config_file))
    if args.doc:
        print(get_schema_doc(schema))
    return 0


if __name__ == '__main__':
    sys.exit(main())


# vi: ts=4 expandtab
