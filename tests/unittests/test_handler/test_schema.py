# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.schema import (
    CLOUD_CONFIG_HEADER, SchemaValidationError, annotated_cloudconfig_file,
    get_schema_doc, get_schema, validate_cloudconfig_file,
    validate_cloudconfig_schema, main)
from cloudinit.util import write_file

from cloudinit.tests.helpers import CiTestCase, mock, skipUnlessJsonSchema

from copy import copy
import os
from six import StringIO
from textwrap import dedent
from yaml import safe_load


class GetSchemaTest(CiTestCase):

    def test_get_schema_coalesces_known_schema(self):
        """Every cloudconfig module with schema is listed in allOf keyword."""
        schema = get_schema()
        self.assertItemsEqual(
            [
                'cc_bootcmd',
                'cc_ntp',
                'cc_resizefs',
                'cc_runcmd',
                'cc_snap',
                'cc_ubuntu_advantage',
                'cc_zypper_add_repo'
            ],
            [subschema['id'] for subschema in schema['allOf']])
        self.assertEqual('cloud-config-schema', schema['id'])
        self.assertEqual(
            'http://json-schema.org/draft-04/schema#',
            schema['$schema'])
        # FULL_SCHEMA is updated by the get_schema call
        from cloudinit.config.schema import FULL_SCHEMA
        self.assertItemsEqual(['id', '$schema', 'allOf'], FULL_SCHEMA.keys())

    def test_get_schema_returns_global_when_set(self):
        """When FULL_SCHEMA global is already set, get_schema returns it."""
        m_schema_path = 'cloudinit.config.schema.FULL_SCHEMA'
        with mock.patch(m_schema_path, {'here': 'iam'}):
            self.assertEqual({'here': 'iam'}, get_schema())


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

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_non_strict_emits_warnings(self):
        """When strict is False validate_cloudconfig_schema emits warnings."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        validate_cloudconfig_schema({'p1': -1}, schema, strict=False)
        self.assertIn(
            "Invalid config:\np1: -1 is not of type 'string'\n",
            self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_emits_warning_on_missing_jsonschema(self):
        """Warning from validate_cloudconfig_schema when missing jsonschema."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        with mock.patch.dict('sys.modules', **{'jsonschema': ImportError()}):
            validate_cloudconfig_schema({'p1': -1}, schema, strict=True)
        self.assertIn(
            'Ignoring schema validation. python-jsonschema is not present',
            self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_strict_raises_errors(self):
        """When strict is True validate_cloudconfig_schema raises errors."""
        schema = {'properties': {'p1': {'type': 'string'}}}
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema({'p1': -1}, schema, strict=True)
        self.assertEqual(
            "Cloud config schema errors: p1: -1 is not of type 'string'",
            str(context_mgr.exception))

    @skipUnlessJsonSchema()
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
            'Cloud config schema errors: format-l1.c1: File {0} needs to begin'
            ' with "{1}"'.format(
                self.config_file, CLOUD_CONFIG_HEADER.decode()),
            str(context_mgr.exception))

    def test_validateconfig_file_error_on_non_yaml_scanner_error(self):
        """On non-yaml scan issues, validate_cloudconfig_file errors."""
        # Generate a scanner error by providing text on a single line with
        # improper indent.
        write_file(self.config_file, '#cloud-config\nasdf:\nasdf')
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertIn(
            'schema errors: format-l3.c1: File {0} is not valid yaml.'.format(
                self.config_file),
            str(context_mgr.exception))

    def test_validateconfig_file_error_on_non_yaml_parser_error(self):
        """On non-yaml parser issues, validate_cloudconfig_file errors."""
        write_file(self.config_file, '#cloud-config\n{}}')
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertIn(
            'schema errors: format-l2.c3: File {0} is not valid yaml.'.format(
                self.config_file),
            str(context_mgr.exception))

    @skipUnlessJsonSchema()
    def test_validateconfig_file_sctrictly_validates_schema(self):
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
                          'items': {'type': 'integer'}}}})
        self.assertEqual(
            dedent("""
                name
                ----
                **Summary:** title

                description

                **Internal name:** ``id``

                **Module frequency:** frequency

                **Supported distros:** debian, rhel

                **Config schema**:
                    **prop1:** (array of integer) prop-description\n\n"""),
            get_schema_doc(full_schema))

    def test_get_schema_doc_handles_multiple_types(self):
        """get_schema_doc delimits multiple property types with a '/'."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'properties': {
                'prop1': {'type': ['string', 'integer'],
                          'description': 'prop-description'}}})
        self.assertIn(
            '**prop1:** (string/integer) prop-description',
            get_schema_doc(full_schema))

    def test_get_schema_doc_handles_enum_types(self):
        """get_schema_doc converts enum types to yaml and delimits with '/'."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'properties': {
                'prop1': {'enum': [True, False, 'stuff'],
                          'description': 'prop-description'}}})
        self.assertIn(
            '**prop1:** (true/false/stuff) prop-description',
            get_schema_doc(full_schema))

    def test_get_schema_doc_handles_nested_oneof_property_types(self):
        """get_schema_doc describes array items oneOf declarations in type."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'properties': {
                'prop1': {'type': 'array',
                          'items': {
                              'oneOf': [{'type': 'string'},
                                        {'type': 'integer'}]},
                          'description': 'prop-description'}}})
        self.assertIn(
            '**prop1:** (array of (string)/(integer)) prop-description',
            get_schema_doc(full_schema))

    def test_get_schema_doc_handles_string_examples(self):
        """get_schema_doc properly indented examples as a list of strings."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {'examples': ['ex1:\n    [don\'t, expand, "this"]', 'ex2: true'],
             'properties': {
                'prop1': {'type': 'array', 'description': 'prop-description',
                          'items': {'type': 'integer'}}}})
        self.assertIn(
            dedent("""
                **Config schema**:
                    **prop1:** (array of integer) prop-description

                **Examples**::

                    ex1:
                        [don't, expand, "this"]
                    # --- Example2 ---
                    ex2: true
            """),
            get_schema_doc(full_schema))

    def test_get_schema_doc_raises_key_errors(self):
        """get_schema_doc raises KeyErrors on missing keys."""
        for key in self.required_schema:
            invalid_schema = copy(self.required_schema)
            invalid_schema.pop(key)
            with self.assertRaises(KeyError) as context_mgr:
                get_schema_doc(invalid_schema)
            self.assertIn(key, str(context_mgr.exception))


class AnnotatedCloudconfigFileTest(CiTestCase):
    maxDiff = None

    def test_annotated_cloudconfig_file_no_schema_errors(self):
        """With no schema_errors, print the original content."""
        content = b'ntp:\n  pools: [ntp1.pools.com]\n'
        self.assertEqual(
            content,
            annotated_cloudconfig_file({}, content, schema_errors=[]))

    def test_annotated_cloudconfig_file_schema_annotates_and_adds_footer(self):
        """With schema_errors, error lines are annotated and a footer added."""
        content = dedent("""\
            #cloud-config
            # comment
            ntp:
              pools: [-99, 75]
            """).encode()
        expected = dedent("""\
            #cloud-config
            # comment
            ntp:		# E1
              pools: [-99, 75]		# E2,E3

            # Errors: -------------
            # E1: Some type error
            # E2: -99 is not a string
            # E3: 75 is not a string

            """)
        parsed_config = safe_load(content[13:])
        schema_errors = [
            ('ntp', 'Some type error'), ('ntp.pools.0', '-99 is not a string'),
            ('ntp.pools.1', '75 is not a string')]
        self.assertEqual(
            expected,
            annotated_cloudconfig_file(parsed_config, content, schema_errors))

    def test_annotated_cloudconfig_file_annotates_separate_line_items(self):
        """Errors are annotated for lists with items on separate lines."""
        content = dedent("""\
            #cloud-config
            # comment
            ntp:
              pools:
                - -99
                - 75
            """).encode()
        expected = dedent("""\
            ntp:
              pools:
                - -99		# E1
                - 75		# E2
            """)
        parsed_config = safe_load(content[13:])
        schema_errors = [
            ('ntp.pools.0', '-99 is not a string'),
            ('ntp.pools.1', '75 is not a string')]
        self.assertIn(
            expected,
            annotated_cloudconfig_file(parsed_config, content, schema_errors))


class MainTest(CiTestCase):

    def test_main_missing_args(self):
        """Main exits non-zero and reports an error on missing parameters."""
        with mock.patch('sys.exit', side_effect=self.sys_exit):
            with mock.patch('sys.argv', ['mycmd']):
                with mock.patch('sys.stderr', new_callable=StringIO) as \
                        m_stderr:
                    with self.assertRaises(SystemExit) as context_manager:
                        main()
        self.assertEqual(1, context_manager.exception.code)
        self.assertEqual(
            'Expected either --config-file argument or --doc\n',
            m_stderr.getvalue())

    def test_main_absent_config_file(self):
        """Main exits non-zero when config file is absent."""
        myargs = ['mycmd', '--annotate', '--config-file', 'NOT_A_FILE']
        with mock.patch('sys.exit', side_effect=self.sys_exit):
            with mock.patch('sys.argv', myargs):
                with mock.patch('sys.stderr', new_callable=StringIO) as \
                        m_stderr:
                    with self.assertRaises(SystemExit) as context_manager:
                        main()
        self.assertEqual(1, context_manager.exception.code)
        self.assertEqual(
            'Configfile NOT_A_FILE does not exist\n',
            m_stderr.getvalue())

    def test_main_prints_docs(self):
        """When --doc parameter is provided, main generates documentation."""
        myargs = ['mycmd', '--doc']
        with mock.patch('sys.argv', myargs):
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(0, main(), 'Expected 0 exit code')
        self.assertIn('\nNTP\n---\n', m_stdout.getvalue())
        self.assertIn('\nRuncmd\n------\n', m_stdout.getvalue())

    def test_main_validates_config_file(self):
        """When --config-file parameter is provided, main validates schema."""
        myyaml = self.tmp_path('my.yaml')
        myargs = ['mycmd', '--config-file', myyaml]
        write_file(myyaml, b'#cloud-config\nntp:')  # shortest ntp schema
        with mock.patch('sys.argv', myargs):
            with mock.patch('sys.stdout', new_callable=StringIO) as m_stdout:
                self.assertEqual(0, main(), 'Expected 0 exit code')
        self.assertIn(
            'Valid cloud-config file {0}'.format(myyaml), m_stdout.getvalue())


class CloudTestsIntegrationTest(CiTestCase):
    """Validate all cloud-config yaml schema provided in integration tests.

    It is less expensive to have unittests validate schema of all cloud-config
    yaml provided to integration tests, than to run an integration test which
    raises Warnings or errors on invalid cloud-config schema.
    """

    @skipUnlessJsonSchema()
    def test_all_integration_test_cloud_config_schema(self):
        """Validate schema of cloud_tests yaml files looking for warnings."""
        schema = get_schema()
        testsdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        integration_testdir = os.path.sep.join(
            [testsdir, 'cloud_tests', 'testcases'])
        errors = []

        yaml_files = []
        for root, _dirnames, filenames in os.walk(integration_testdir):
            yaml_files.extend([os.path.join(root, f)
                               for f in filenames if f.endswith(".yaml")])
        self.assertTrue(len(yaml_files) > 0)

        for filename in yaml_files:
            test_cfg = safe_load(open(filename))
            cloud_config = test_cfg.get('cloud_config')
            if cloud_config:
                cloud_config = safe_load(
                    cloud_config.replace("#cloud-config\n", ""))
                try:
                    validate_cloudconfig_schema(
                        cloud_config, schema, strict=True)
                except SchemaValidationError as e:
                    errors.append(
                        '{0}: {1}'.format(
                            filename, e))
        if errors:
            raise AssertionError(', '.join(errors))

# vi: ts=4 expandtab syntax=python
