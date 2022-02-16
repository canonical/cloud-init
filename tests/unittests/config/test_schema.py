# This file is part of cloud-init. See LICENSE file for license information.


import importlib
import inspect
import itertools
import logging
import sys
from copy import copy
from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from yaml import safe_load

from cloudinit.config.schema import (
    CLOUD_CONFIG_HEADER,
    MetaSchema,
    SchemaValidationError,
    _schemapath_for_cloudconfig,
    annotated_cloudconfig_file,
    get_jsonschema_validator,
    get_meta_doc,
    get_schema,
    load_doc,
    main,
    validate_cloudconfig_file,
    validate_cloudconfig_metaschema,
    validate_cloudconfig_schema,
)
from cloudinit.util import write_file
from tests.unittests.helpers import (
    CiTestCase,
    cloud_init_project_dir,
    mock,
    skipUnlessJsonSchema,
)


def get_schemas() -> dict:
    """Return all legacy module schemas

    Assumes that module schemas have the variable name "schema"
    """
    return get_module_variable("schema")


def get_metas() -> dict:
    """Return all module metas

    Assumes that module schemas have the variable name "schema"
    """
    return get_module_variable("meta")


def get_module_variable(var_name) -> dict:
    """Inspect modules and get variable from module matching var_name"""
    schemas = {}

    files = list(
        Path(cloud_init_project_dir("cloudinit/config/")).glob("cc_*.py")
    )

    modules = [mod.stem for mod in files]

    for module in modules:
        importlib.import_module("cloudinit.config.{}".format(module))

    for k, v in sys.modules.items():
        path = Path(k)

        if "cloudinit.config" == path.stem and path.suffix[1:4] == "cc_":
            module_name = path.suffix[1:]
            members = inspect.getmembers(v)
            schemas[module_name] = None
            for name, value in members:
                if name == var_name:
                    schemas[module_name] = value
                    break
    return schemas


class TestGetSchema:
    def test_get_schema_coalesces_known_schema(self):
        """Every cloudconfig module with schema is listed in allOf keyword."""
        schema = get_schema()
        assert sorted(
            [
                "cc_apk_configure",
                "cc_apt_configure",
                "cc_apt_pipelining",
                "cc_bootcmd",
                "cc_byobu",
                "cc_ca_certs",
                "cc_chef",
                "cc_debug",
                "cc_disable_ec2_metadata",
                "cc_disk_setup",
                "cc_install_hotplug",
                "cc_keyboard",
                "cc_locale",
                "cc_ntp",
                "cc_resizefs",
                "cc_runcmd",
                "cc_snap",
                "cc_ubuntu_advantage",
                "cc_ubuntu_drivers",
                "cc_write_files",
                "cc_zypper_add_repo",
            ]
        ) == sorted(
            [meta["id"] for meta in get_metas().values() if meta is not None]
        )
        assert "http://json-schema.org/draft-04/schema#" == schema["$schema"]
        assert ["$defs", "$schema", "allOf"] == sorted(list(schema.keys()))
        # New style schema should be defined in static schema file in $defs
        expected_subschema_defs = [
            {"$ref": "#/$defs/cc_apk_configure"},
            {"$ref": "#/$defs/cc_apt_configure"},
            {"$ref": "#/$defs/cc_apt_pipelining"},
            {"$ref": "#/$defs/cc_bootcmd"},
            {"$ref": "#/$defs/cc_byobu"},
            {"$ref": "#/$defs/cc_ca_certs"},
            {"$ref": "#/$defs/cc_chef"},
            {"$ref": "#/$defs/cc_debug"},
            {"$ref": "#/$defs/cc_disable_ec2_metadata"},
            {"$ref": "#/$defs/cc_disk_setup"},
        ]
        found_subschema_defs = []
        legacy_schema_keys = []
        for subschema in schema["allOf"]:
            if "$ref" in subschema:
                found_subschema_defs.append(subschema)
            else:  # Legacy subschema sourced from cc_* module 'schema' attr
                legacy_schema_keys.extend(subschema["properties"].keys())

        assert expected_subschema_defs == found_subschema_defs
        # This list will dwindle as we move legacy schema to new $defs
        assert [
            "drivers",
            "keyboard",
            "locale",
            "locale_configfile",
            "ntp",
            "resize_rootfs",
            "runcmd",
            "snap",
            "ubuntu_advantage",
            "updates",
            "write_files",
            "write_files",
            "zypper",
        ] == sorted(legacy_schema_keys)


class TestLoadDoc:

    docs = get_module_variable("__doc__")

    # TODO( Drop legacy test when all sub-schemas in cloud-init-schema.json )
    @pytest.mark.parametrize(
        "module_name",
        (
            "cc_apt_pipelining",  # new style composite schema file
            "cc_zypper_add_repo",  # legacy sub-schema defined in module
        ),
    )
    def test_report_docs_for_legacy_and_consolidated_schema(self, module_name):
        doc = load_doc([module_name])
        assert doc, "Unexpected empty docs for {}".format(module_name)
        assert self.docs[module_name] == doc


class Test_SchemapathForCloudconfig:
    """Coverage tests for supported YAML formats."""

    @pytest.mark.parametrize(
        "source_content, expected",
        (
            (b"{}", {}),  # assert empty config handled
            # Multiple keys account for comments and whitespace lines
            (b"#\na: va\n  \nb: vb\n#\nc: vc", {"a": 2, "b": 4, "c": 6}),
            # List items represented on correct line number
            (b"a:\n - a1\n\n - a2\n", {"a": 1, "a.0": 2, "a.1": 4}),
            # Nested dicts represented on correct line number
            (b"a:\n a1:\n\n  aa1: aa1v\n", {"a": 1, "a.a1": 2, "a.a1.aa1": 4}),
        ),
    )
    def test_schemapaths_representatative_of_source_yaml(
        self, source_content, expected
    ):
        """Validate schemapaths dict accurately represents source YAML line."""
        cfg = yaml.safe_load(source_content)
        assert expected == _schemapath_for_cloudconfig(
            config=cfg, original_content=source_content
        )


class SchemaValidationErrorTest(CiTestCase):
    """Test validate_cloudconfig_schema"""

    def test_schema_validation_error_expects_schema_errors(self):
        """SchemaValidationError is initialized from schema_errors."""
        errors = (
            ("key.path", 'unexpected key "junk"'),
            ("key2.path", '"-123" is not a valid "hostname" format'),
        )
        exception = SchemaValidationError(schema_errors=errors)
        self.assertIsInstance(exception, Exception)
        self.assertEqual(exception.schema_errors, errors)
        self.assertEqual(
            'Cloud config schema errors: key.path: unexpected key "junk", '
            'key2.path: "-123" is not a valid "hostname" format',
            str(exception),
        )
        self.assertTrue(isinstance(exception, ValueError))


class TestValidateCloudConfigSchema:
    """Tests for validate_cloudconfig_schema."""

    with_logs = True

    @pytest.mark.parametrize(
        "schema, call_count",
        ((None, 1), ({"properties": {"p1": {"type": "string"}}}, 0)),
    )
    @skipUnlessJsonSchema()
    @mock.patch("cloudinit.config.schema.get_schema")
    def test_validateconfig_schema_use_full_schema_when_no_schema_param(
        self, get_schema, schema, call_count
    ):
        """Use full schema when schema param is absent."""
        get_schema.return_value = {"properties": {"p1": {"type": "string"}}}
        kwargs = {"config": {"p1": "valid"}}
        if schema:
            kwargs["schema"] = schema
        validate_cloudconfig_schema(**kwargs)
        assert call_count == get_schema.call_count

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_non_strict_emits_warnings(self, caplog):
        """When strict is False validate_cloudconfig_schema emits warnings."""
        schema = {"properties": {"p1": {"type": "string"}}}
        validate_cloudconfig_schema({"p1": -1}, schema, strict=False)
        [(module, log_level, log_msg)] = caplog.record_tuples
        assert "cloudinit.config.schema" == module
        assert logging.WARNING == log_level
        assert (
            "Invalid cloud-config provided:\np1: -1 is not of type 'string'"
            == log_msg
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_emits_warning_on_missing_jsonschema(
        self, caplog
    ):
        """Warning from validate_cloudconfig_schema when missing jsonschema."""
        schema = {"properties": {"p1": {"type": "string"}}}
        with mock.patch.dict("sys.modules", **{"jsonschema": ImportError()}):
            validate_cloudconfig_schema({"p1": -1}, schema, strict=True)
        assert "Ignoring schema validation. jsonschema is not present" in (
            caplog.text
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_strict_raises_errors(self):
        """When strict is True validate_cloudconfig_schema raises errors."""
        schema = {"properties": {"p1": {"type": "string"}}}
        with pytest.raises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema({"p1": -1}, schema, strict=True)
        assert (
            "Cloud config schema errors: p1: -1 is not of type 'string'"
            == (str(context_mgr.value))
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_honors_formats(self):
        """With strict True, validate_cloudconfig_schema errors on format."""
        schema = {"properties": {"p1": {"type": "string", "format": "email"}}}
        with pytest.raises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema({"p1": "-1"}, schema, strict=True)
        assert "Cloud config schema errors: p1: '-1' is not a 'email'" == (
            str(context_mgr.value)
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_schema_honors_formats_strict_metaschema(self):
        """With strict and strict_metaschema True, ensure errors on format"""
        schema = {"properties": {"p1": {"type": "string", "format": "email"}}}
        with pytest.raises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_schema(
                {"p1": "-1"}, schema, strict=True, strict_metaschema=True
            )
        assert "Cloud config schema errors: p1: '-1' is not a 'email'" == str(
            context_mgr.value
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_strict_metaschema_do_not_raise_exception(
        self, caplog
    ):
        """With strict_metaschema=True, do not raise exceptions.

        This flag is currently unused, but is intended for run-time validation.
        This should warn, but not raise.
        """
        schema = {"properties": {"p1": {"types": "string", "format": "email"}}}
        validate_cloudconfig_schema(
            {"p1": "-1"}, schema, strict_metaschema=True
        )
        assert (
            "Meta-schema validation failed, attempting to validate config"
            in caplog.text
        )


class TestCloudConfigExamples:
    metas = get_metas()
    params = [
        (meta["id"], example)
        for meta in metas.values()
        if meta and meta.get("examples")
        for example in meta.get("examples")
    ]

    @pytest.mark.parametrize("schema_id, example", params)
    @skipUnlessJsonSchema()
    def test_validateconfig_schema_of_example(self, schema_id, example):
        """For a given example in a config module we test if it is valid
        according to the unified schema of all config modules
        """
        schema = get_schema()
        config_load = safe_load(example)
        validate_cloudconfig_schema(config_load, schema, strict=True)


class ValidateCloudConfigFileTest(CiTestCase):
    """Tests for validate_cloudconfig_file."""

    def setUp(self):
        super(ValidateCloudConfigFileTest, self).setUp()
        self.config_file = self.tmp_path("cloudcfg.yaml")

    def test_validateconfig_file_error_on_absent_file(self):
        """On absent config_path, validate_cloudconfig_file errors."""
        with self.assertRaises(RuntimeError) as context_mgr:
            validate_cloudconfig_file("/not/here", {})
        self.assertEqual(
            "Configfile /not/here does not exist", str(context_mgr.exception)
        )

    def test_validateconfig_file_error_on_invalid_header(self):
        """On invalid header, validate_cloudconfig_file errors.

        A SchemaValidationError is raised when the file doesn't begin with
        CLOUD_CONFIG_HEADER.
        """
        write_file(self.config_file, "#junk")
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertEqual(
            "Cloud config schema errors: format-l1.c1: File {0} needs to begin"
            ' with "{1}"'.format(
                self.config_file, CLOUD_CONFIG_HEADER.decode()
            ),
            str(context_mgr.exception),
        )

    def test_validateconfig_file_error_on_non_yaml_scanner_error(self):
        """On non-yaml scan issues, validate_cloudconfig_file errors."""
        # Generate a scanner error by providing text on a single line with
        # improper indent.
        write_file(self.config_file, "#cloud-config\nasdf:\nasdf")
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertIn(
            "schema errors: format-l3.c1: File {0} is not valid yaml.".format(
                self.config_file
            ),
            str(context_mgr.exception),
        )

    def test_validateconfig_file_error_on_non_yaml_parser_error(self):
        """On non-yaml parser issues, validate_cloudconfig_file errors."""
        write_file(self.config_file, "#cloud-config\n{}}")
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, {})
        self.assertIn(
            "schema errors: format-l2.c3: File {0} is not valid yaml.".format(
                self.config_file
            ),
            str(context_mgr.exception),
        )

    @skipUnlessJsonSchema()
    def test_validateconfig_file_sctrictly_validates_schema(self):
        """validate_cloudconfig_file raises errors on invalid schema."""
        schema = {"properties": {"p1": {"type": "string", "format": "string"}}}
        write_file(self.config_file, "#cloud-config\np1: -1")
        with self.assertRaises(SchemaValidationError) as context_mgr:
            validate_cloudconfig_file(self.config_file, schema)
        self.assertEqual(
            "Cloud config schema errors: p1: -1 is not of type 'string'",
            str(context_mgr.exception),
        )


class GetSchemaDocTest(CiTestCase):
    """Tests for get_meta_doc."""

    def setUp(self):
        super(GetSchemaDocTest, self).setUp()
        self.required_schema = {
            "title": "title",
            "description": "description",
            "id": "id",
            "name": "name",
            "frequency": "frequency",
            "distros": ["debian", "rhel"],
        }
        self.meta: MetaSchema = {
            "title": "title",
            "description": "description",
            "id": "id",
            "name": "name",
            "frequency": "frequency",
            "distros": ["debian", "rhel"],
            "examples": [
                'ex1:\n    [don\'t, expand, "this"]',
                "ex2: true",
            ],
        }

    def test_get_meta_doc_returns_restructured_text(self):
        """get_meta_doc returns restructured text for a cloudinit schema."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {
                "properties": {
                    "prop1": {
                        "type": "array",
                        "description": "prop-description",
                        "items": {"type": "integer"},
                    }
                }
            }
        )

        doc = get_meta_doc(self.meta, full_schema)
        self.assertEqual(
            dedent(
                """
                name
                ----
                **Summary:** title

                description

                **Internal name:** ``id``

                **Module frequency:** frequency

                **Supported distros:** debian, rhel

                **Config schema**:
                    **prop1:** (array of integer) prop-description

                **Examples**::

                    ex1:
                        [don't, expand, "this"]
                    # --- Example2 ---
                    ex2: true
            """
            ),
            doc,
        )

    def test_get_meta_doc_handles_multiple_types(self):
        """get_meta_doc delimits multiple property types with a '/'."""
        schema = {"properties": {"prop1": {"type": ["string", "integer"]}}}
        self.assertIn(
            "**prop1:** (string/integer)", get_meta_doc(self.meta, schema)
        )

    def test_get_meta_doc_handles_enum_types(self):
        """get_meta_doc converts enum types to yaml and delimits with '/'."""
        schema = {"properties": {"prop1": {"enum": [True, False, "stuff"]}}}
        self.assertIn(
            "**prop1:** (true/false/stuff)", get_meta_doc(self.meta, schema)
        )

    def test_get_meta_doc_handles_nested_oneof_property_types(self):
        """get_meta_doc describes array items oneOf declarations in type."""
        schema = {
            "properties": {
                "prop1": {
                    "type": "array",
                    "items": {
                        "oneOf": [{"type": "string"}, {"type": "integer"}]
                    },
                }
            }
        }
        self.assertIn(
            "**prop1:** (array of (string)/(integer))",
            get_meta_doc(self.meta, schema),
        )

    def test_get_meta_doc_handles_string_examples(self):
        """get_meta_doc properly indented examples as a list of strings."""
        full_schema = copy(self.required_schema)
        full_schema.update(
            {
                "examples": [
                    'ex1:\n    [don\'t, expand, "this"]',
                    "ex2: true",
                ],
                "properties": {
                    "prop1": {
                        "type": "array",
                        "description": "prop-description",
                        "items": {"type": "integer"},
                    }
                },
            }
        )
        self.assertIn(
            dedent(
                """
                **Config schema**:
                    **prop1:** (array of integer) prop-description

                **Examples**::

                    ex1:
                        [don't, expand, "this"]
                    # --- Example2 ---
                    ex2: true
            """
            ),
            get_meta_doc(self.meta, full_schema),
        )

    def test_get_meta_doc_properly_parse_description(self):
        """get_meta_doc description properly formatted"""
        schema = {
            "properties": {
                "p1": {
                    "type": "string",
                    "description": dedent(
                        """\
                        This item
                        has the
                        following options:

                          - option1
                          - option2
                          - option3

                        The default value is
                        option1"""
                    ),
                }
            }
        }

        self.assertIn(
            dedent(
                """
                **Config schema**:
                    **p1:** (string) This item has the following options:

                            - option1
                            - option2
                            - option3

                    The default value is option1

            """
            ),
            get_meta_doc(self.meta, schema),
        )

    def test_get_meta_doc_raises_key_errors(self):
        """get_meta_doc raises KeyErrors on missing keys."""
        schema = {
            "properties": {
                "prop1": {
                    "type": "array",
                    "items": {
                        "oneOf": [{"type": "string"}, {"type": "integer"}]
                    },
                }
            }
        }
        for key in self.meta:
            invalid_meta = copy(self.meta)
            invalid_meta.pop(key)
            with self.assertRaises(KeyError) as context_mgr:
                get_meta_doc(invalid_meta, schema)
            self.assertIn(key, str(context_mgr.exception))

    def test_label_overrides_property_name(self):
        """get_meta_doc overrides property name with label."""
        schema = {
            "properties": {
                "prop1": {
                    "type": "string",
                    "label": "label1",
                },
                "prop_no_label": {
                    "type": "string",
                },
                "prop_array": {
                    "label": "array_label",
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "some_prop": {"type": "number"},
                        },
                    },
                },
            },
            "patternProperties": {
                "^.*$": {
                    "type": "string",
                    "label": "label2",
                }
            },
        }
        meta_doc = get_meta_doc(self.meta, schema)
        assert "**label1:** (string)" in meta_doc
        assert "**label2:** (string" in meta_doc
        assert "**prop_no_label:** (string)" in meta_doc
        assert "Each item in **array_label** list" in meta_doc

        assert "prop1" not in meta_doc
        assert ".*" not in meta_doc


class AnnotatedCloudconfigFileTest(CiTestCase):
    maxDiff = None

    def test_annotated_cloudconfig_file_no_schema_errors(self):
        """With no schema_errors, print the original content."""
        content = b"ntp:\n  pools: [ntp1.pools.com]\n"
        self.assertEqual(
            content, annotated_cloudconfig_file({}, content, schema_errors=[])
        )

    def test_annotated_cloudconfig_file_with_non_dict_cloud_config(self):
        """Error when empty non-dict cloud-config is provided.

        OurJSON validation when user-data is None type generates a bunch
        schema validation errors of the format:
        ('', "None is not of type 'object'"). Ignore those symptoms and
        report the general problem instead.
        """
        content = b"\n\n\n"
        expected = "\n".join(
            [
                content.decode(),
                "# Errors: -------------",
                "# E1: Cloud-config is not a YAML dict.\n\n",
            ]
        )
        self.assertEqual(
            expected,
            annotated_cloudconfig_file(
                None,
                content,
                schema_errors=[("", "None is not of type 'object'")],
            ),
        )

    def test_annotated_cloudconfig_file_schema_annotates_and_adds_footer(self):
        """With schema_errors, error lines are annotated and a footer added."""
        content = dedent(
            """\
            #cloud-config
            # comment
            ntp:
              pools: [-99, 75]
            """
        ).encode()
        expected = dedent(
            """\
            #cloud-config
            # comment
            ntp:		# E1
              pools: [-99, 75]		# E2,E3

            # Errors: -------------
            # E1: Some type error
            # E2: -99 is not a string
            # E3: 75 is not a string

            """
        )
        parsed_config = safe_load(content[13:])
        schema_errors = [
            ("ntp", "Some type error"),
            ("ntp.pools.0", "-99 is not a string"),
            ("ntp.pools.1", "75 is not a string"),
        ]
        self.assertEqual(
            expected,
            annotated_cloudconfig_file(parsed_config, content, schema_errors),
        )

    def test_annotated_cloudconfig_file_annotates_separate_line_items(self):
        """Errors are annotated for lists with items on separate lines."""
        content = dedent(
            """\
            #cloud-config
            # comment
            ntp:
              pools:
                - -99
                - 75
            """
        ).encode()
        expected = dedent(
            """\
            ntp:
              pools:
                - -99		# E1
                - 75		# E2
            """
        )
        parsed_config = safe_load(content[13:])
        schema_errors = [
            ("ntp.pools.0", "-99 is not a string"),
            ("ntp.pools.1", "75 is not a string"),
        ]
        self.assertIn(
            expected,
            annotated_cloudconfig_file(parsed_config, content, schema_errors),
        )


class TestMain:

    exclusive_combinations = itertools.combinations(
        ["--system", "--docs all", "--config-file something"], 2
    )

    @pytest.mark.parametrize("params", exclusive_combinations)
    def test_main_exclusive_args(self, params, capsys):
        """Main exits non-zero and error on required exclusive args."""
        params = list(itertools.chain(*[a.split() for a in params]))
        with mock.patch("sys.argv", ["mycmd"] + params):
            with pytest.raises(SystemExit) as context_manager:
                main()
        assert 1 == context_manager.value.code

        _out, err = capsys.readouterr()
        expected = (
            "Error:\n"
            "Expected one of --config-file, --system or --docs arguments\n"
        )
        assert expected == err

    def test_main_missing_args(self, capsys):
        """Main exits non-zero and reports an error on missing parameters."""
        with mock.patch("sys.argv", ["mycmd"]):
            with pytest.raises(SystemExit) as context_manager:
                main()
        assert 1 == context_manager.value.code

        _out, err = capsys.readouterr()
        expected = (
            "Error:\n"
            "Expected one of --config-file, --system or --docs arguments\n"
        )
        assert expected == err

    def test_main_absent_config_file(self, capsys):
        """Main exits non-zero when config file is absent."""
        myargs = ["mycmd", "--annotate", "--config-file", "NOT_A_FILE"]
        with mock.patch("sys.argv", myargs):
            with pytest.raises(SystemExit) as context_manager:
                main()
        assert 1 == context_manager.value.code
        _out, err = capsys.readouterr()
        assert "Error:\nConfigfile NOT_A_FILE does not exist\n" == err

    def test_main_invalid_flag_combo(self, capsys):
        """Main exits non-zero when invalid flag combo used."""
        myargs = ["mycmd", "--annotate", "--docs", "DOES_NOT_MATTER"]
        with mock.patch("sys.argv", myargs):
            with pytest.raises(SystemExit) as context_manager:
                main()
        assert 1 == context_manager.value.code
        _, err = capsys.readouterr()
        assert (
            "Error:\nInvalid flag combination. "
            "Cannot use --annotate with --docs\n" == err
        )

    def test_main_prints_docs(self, capsys):
        """When --docs parameter is provided, main generates documentation."""
        myargs = ["mycmd", "--docs", "all"]
        with mock.patch("sys.argv", myargs):
            assert 0 == main(), "Expected 0 exit code"
        out, _err = capsys.readouterr()
        assert "\nNTP\n---\n" in out
        assert "\nRuncmd\n------\n" in out

    def test_main_validates_config_file(self, tmpdir, capsys):
        """When --config-file parameter is provided, main validates schema."""
        myyaml = tmpdir.join("my.yaml")
        myargs = ["mycmd", "--config-file", myyaml.strpath]
        myyaml.write(b"#cloud-config\nntp:")  # shortest ntp schema
        with mock.patch("sys.argv", myargs):
            assert 0 == main(), "Expected 0 exit code"
        out, _err = capsys.readouterr()
        assert "Valid cloud-config: {0}\n".format(myyaml) == out

    @mock.patch("cloudinit.config.schema.read_cfg_paths")
    @mock.patch("cloudinit.config.schema.os.getuid", return_value=0)
    def test_main_validates_system_userdata(
        self, m_getuid, m_read_cfg_paths, capsys, paths
    ):
        """When --system is provided, main validates system userdata."""
        m_read_cfg_paths.return_value = paths
        ud_file = paths.get_ipath_cur("userdata_raw")
        write_file(ud_file, b"#cloud-config\nntp:")
        myargs = ["mycmd", "--system"]
        with mock.patch("sys.argv", myargs):
            assert 0 == main(), "Expected 0 exit code"
        out, _err = capsys.readouterr()
        assert "Valid cloud-config: system userdata\n" == out

    @mock.patch("cloudinit.config.schema.os.getuid", return_value=1000)
    def test_main_system_userdata_requires_root(self, m_getuid, capsys, paths):
        """Non-root user can't use --system param"""
        myargs = ["mycmd", "--system"]
        with mock.patch("sys.argv", myargs):
            with pytest.raises(SystemExit) as context_manager:
                main()
        assert 1 == context_manager.value.code
        _out, err = capsys.readouterr()
        expected = (
            "Error:\nUnable to read system userdata as non-root user. "
            "Try using sudo\n"
        )
        assert expected == err


def _get_meta_doc_examples():
    examples_dir = Path(cloud_init_project_dir("doc/examples"))
    assert examples_dir.is_dir()

    return (
        str(f)
        for f in examples_dir.glob("cloud-config*.txt")
        if not f.name.startswith("cloud-config-archive")
    )


class TestSchemaDocExamples:
    schema = get_schema()

    @pytest.mark.parametrize("example_path", _get_meta_doc_examples())
    @skipUnlessJsonSchema()
    def test_schema_doc_examples(self, example_path):
        validate_cloudconfig_file(example_path, self.schema)


class TestStrictMetaschema:
    """Validate that schemas follow a stricter metaschema definition than
    the default. This disallows arbitrary key/value pairs.
    """

    @skipUnlessJsonSchema()
    def test_modules(self):
        """Validate all modules with a stricter metaschema"""
        (validator, _) = get_jsonschema_validator()
        for (name, value) in get_schemas().items():
            if value:
                validate_cloudconfig_metaschema(validator, value)
            else:
                logging.warning("module %s has no schema definition", name)

    @skipUnlessJsonSchema()
    def test_validate_bad_module(self):
        """Throw exception by default, don't throw if throw=False

        item should be 'items' and is therefore interpreted as an additional
        property which is invalid with a strict metaschema
        """
        (validator, _) = get_jsonschema_validator()
        schema = {
            "type": "array",
            "item": {
                "type": "object",
            },
        }
        with pytest.raises(
            SchemaValidationError,
            match=r"Additional properties are not allowed.*",
        ):

            validate_cloudconfig_metaschema(validator, schema)

        validate_cloudconfig_metaschema(validator, schema, throw=False)


# vi: ts=4 expandtab syntax=python
