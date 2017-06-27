# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.schema import (
    CLOUD_CONFIG_HEADER, SchemaValidationError, get_schema_doc,
    validate_cloudconfig_file, validate_cloudconfig_schema,
    main)
from cloudinit.util import write_file

from ..helpers import CiTestCase, mock, skipIf

from copy import copy
from six import StringIO
from textwrap import dedent

try:
    import jsonschema
    assert jsonschema  # avoid pyflakes error F401: import unused
    _missing_jsonschema_dep = False
except ImportError:
    _missing_jsonschema_dep = True


class SchemaValidationErrorTest(CiTestCase):
    """Test validate_cloudconfig_schema"""

    def test_schema_validation_error_expects_schema_errors(self):
        """SchemaValidationError is initialized from schema_errors."""
        errors = (('key.path', 'unexpected key "junk"'),
                  ('key2.path', '"-123" is not a valid "hostname" format'))
        exception = SchemaValidationError(schema_errors=errors)
        self.assertIsInstance(exception, Exception)
        self.assertEqual(exception.schema_errors, errors)
        self.assertEqual(
            'Cloud config schema errors: key.path: unexpected key "junk", '
            'key2.path: "-123" is not a valid "hostname" format',
            str(exception))
        self.assertTrue(isinstance(exception, ValueError))


class ValidateCloudConfigSchemaTest(CiTestCase):
    """Tests for validate_cloudconfig_schema."""

    with_logs = True

    @skipIf(_missing_jsonschema_dep, "No python-jsonschema dependency")
    def test_validateconfig_schema_non_strict_emits_warnings(self):
        """When strict is False validate_cloudconfig_schema emits warnings."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        validate_cloudconfig_schema({'p1': -1}, schema, strict=False)
        self.assertIn(
            "Invalid config:\np1: -1 is not of type 'string'\n",
            self.logs.getvalue())

    @skipIf(_missing_jsonschema_dep, "No python-jsonschema dependency")
    def test_validateconfig_schema_emits_warning_on_missing_jsonschema(self):
        """Warning from validate_cloudconfig_schema when missing jsonschema."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        with mock.patch.dict('sys.modules', **{'jsonschema': ImportError()}):
            validate_cloudconfig_schema({'p1': -1}, schema, strict=True)
        self.assertIn(
            'Ignoring schema validation. python-jsonschema is not present',
            self.logs.getvalue())

    @skipIf(_missing_jsonschema_dep, "No python-jsonschema dependency")
    def test_validateconfig_schema_strict_raises_errors(self):
        """When strict is True validate_cloudconfig_schema raises errors."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema({'p1': -1}, schema, strict=True)
        self.assertEqual(
            "Cloud config schema errors: p1: -1 is not of type 'string'",
            str(context_mgr.exception))

    @skipIf(_missing_jsonschema_dep, "No python-jsonschema dependency")
    def test_validateconfig_schema_honors_formats(self):
        """With strict True, validate_cloudconfig_schema errors on format."""
        schema = {
            'properties': {'p1': {'type': 'string', 'format': 'hostname'}}}
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema({'p1': '-1'}, schema, strict=True)
        self.assertEqual(
            "Cloud config schema errors: p1: '-1' is not a 'hostname'",
            str(context_mgr.exception))


class ValidateCloudConfigFileTest(CiTestCase):
    """Tests for validate_cloudconfig_file."""

    def setUp(self):
        super(ValidateCloudConfigFileTest, self).setUp()
        self.config_file = self.tmp_path('cloudcfg.yaml')

    def test_validateconfig_file_error_on_absent_file(self):
        """On absent config_path, validate_cloudconfig_file errors."""
        with self.assertRaises(RuntimeError) as context_mgr:
            validate_cloudconfig_file('/not/here', {})
        self.assertEqual(
            'Configfile /not/here does not exist',
            str(context_mgr.exception))

    def test_validateconfig_file_error_on_invalid_header(self):
        """On invalid header, validate_cloudconfig_file errors.

        A SchemaValidationError is raised when the file doesn't begin with
        CLOUD_CONFIG_HEADER.
        """
        write_file(self.config_file, '#junk')
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertEqual(
            'Cloud config schema errors: header: File {0} needs to begin with '
            '"{1}"'.format(self.config_file, CLOUD_CONFIG_HEADER.decode()),
            str(context_mgr.exception))

    def test_validateconfig_file_error_on_non_yaml_format(self):
        """On non-yaml format, validate_cloudconfig_file errors."""
        write_file(self.config_file, '#cloud-config\n{}}')
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertIn(
            'schema errors: format: File {0} is not valid yaml.'.format(
                self.config_file),
            str(context_mgr.exception))

    @skipIf(_missing_jsonschema_dep, "No python-jsonschema dependency")
    def test_validateconfig_file_sctricty_validates_schema(self):
        """validate_cloudconfig_file raises errors on invalid schema."""
        schema = {
            'properties': {'p1': {'type': 'string', 'format': 'hostname'}}}
        write_file(self.config_file, '#cloud-config\np1: "-1"')
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, schema)
        self.assertEqual(
            "Cloud config schema errors: p1: '-1' is not a 'hostname'",
            str(context_mgr.exception))


class GetSchemaDocTest(CiTestCase):
    """Tests for get_schema_doc."""

    def setUp(self):
        super(GetSchemaDocTest, self).setUp()
        self.required_schema = {
            'title': 'title', 'description': 'description', 'id': 'id',
            'name': 'name', 'frequency': 'frequency',
            'distros': ['debian', 'rhel']}

    def test_get_schema_doc_returns_restructured_text(self):
        """get_schema_doc returns restructured text for a cloudinit schema."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'properties': {
                'prop1': {'type': 'array', 'description': 'prop-description',
                          'items': {'type': 'int'}}}})
        self.assertEqual(
            dedent("""
                name
                ---
                **Summary:** title

                description

                **Internal name:** ``id``

                **Module frequency:** frequency

                **Supported distros:** debian, rhel

                **Config schema**:
                    **prop1:** (array of int) prop-description\n\n"""),
            get_schema_doc(full_schema))

    def test_get_schema_doc_returns_restructured_text_with_examples(self):
        """get_schema_doc returns indented examples when present in schema."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'examples': {'ex1': [1, 2, 3]},
             'properties': {
                'prop1': {'type': 'array', 'description': 'prop-description',
                          'items': {'type': 'int'}}}})
        self.assertIn(
            dedent("""
                **Config schema**:
                    **prop1:** (array of int) prop-description

                **Examples**::

                    ex1"""),
            get_schema_doc(full_schema))

    def test_get_schema_doc_raises_key_errors(self):
        """get_schema_doc raises KeyErrors on missing keys."""
        for key in self.required_schema:
            invalid_schema = copy(self.required_schema)
            invalid_schema.pop(key)
            with self.assertRaises(KeyError) as context_mgr:
                get_schema_doc(invalid_schema)
            self.assertIn(key, str(context_mgr.exception))


class MainTest(CiTestCase):

    def test_main_missing_args(self):
        """Main exits non-zero and reports an error on missing parameters."""
        with mock.patch('sys.argv', ['mycmd']):
            with mock.patch('sys.stderr', new_callable=StringIO) as m_stderr:
                self.assertEqual(1, main(), 'Expected non-zero exit code')
        self.assertEqual(
            'Expected either --config-file argument or --doc\n',
            m_stderr.getvalue())

    def test_main_prints_docs(self):
        """When --doc parameter is provided, main generates documentation."""
        myargs = ['mycmd', '--doc']
        with mock.patch('sys.argv', myargs):
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(0, main(), 'Expected 0 exit code')
        self.assertIn('\nNTP\n---\n', m_stdout.getvalue())

    def test_main_validates_config_file(self):
        """When --config-file parameter is provided, main validates schema."""
        myyaml = self.tmp_path('my.yaml')
        myargs = ['mycmd', '--config-file', myyaml]
        with open(myyaml, 'wb') as stream:
            stream.write(b'#cloud-config\nntp:')   # shortest ntp schema
        with mock.patch('sys.argv', myargs):
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(0, main(), 'Expected 0 exit code')
        self.assertIn(
            'Valid cloud-config file {0}'.format(myyaml), m_stdout.getvalue())

# vi: ts=4 expandtab syntax=python
