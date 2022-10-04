# This file is part of cloud-init. See LICENSE file for license information.


import importlib
import inspect
import itertools
import json
import logging
import os
import re
import sys
from collections import namedtuple
from copy import deepcopy
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from typing import List, Optional, Sequence, Set

import pytest
import responses

from cloudinit import stages
from cloudinit.config.schema import (
    CLOUD_CONFIG_HEADER,
    VERSIONED_USERDATA_SCHEMA_FILE,
    MetaSchema,
    SchemaProblem,
    SchemaValidationError,
    annotated_cloudconfig_file,
    get_jsonschema_validator,
    get_meta_doc,
    get_schema,
    get_schema_dir,
    handle_schema_args,
    load_doc,
    main,
    validate_cloudconfig_file,
    validate_cloudconfig_metaschema,
    validate_cloudconfig_schema,
)
from cloudinit.distros import OSFAMILIES
from cloudinit.safeyaml import load, load_with_marks
from cloudinit.settings import FREQUENCIES
from cloudinit.util import load_file, write_file
from tests.hypothesis import given
from tests.hypothesis_jsonschema import from_schema
from tests.unittests.helpers import (
    CiTestCase,
    cloud_init_project_dir,
    does_not_raise,
    mock,
    skipUnlessHypothesisJsonSchema,
    skipUnlessJsonSchema,
)
from tests.unittests.util import FakeDataSource

M_PATH = "cloudinit.config.schema."


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


def get_module_names() -> List[str]:
    """Return list of module names in cloudinit/config"""
    files = list(
        Path(cloud_init_project_dir("cloudinit/config/")).glob("cc_*.py")
    )

    return [mod.stem for mod in files]


def get_modules() -> List[ModuleType]:
    """Return list of modules in cloudinit/config"""
    return [
        importlib.import_module(f"cloudinit.config.{module}")
        for module in get_module_names()
    ]


def get_module_variable(var_name) -> dict:
    """Inspect modules and get variable from module matching var_name"""
    schemas: dict = {}
    get_modules()
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


class TestVersionedSchemas:
    @pytest.mark.parametrize(
        "schema,error_msg",
        (
            ({}, None),
            ({"version": "v1"}, None),
            ({"version": "v2"}, "is not valid"),
            ({"version": "v1", "final_message": -1}, "is not valid"),
            ({"version": "v1", "final_message": "some msg"}, None),
        ),
    )
    def test_versioned_cloud_config_schema_is_valid_json(
        self, schema, error_msg
    ):
        schema_dir = get_schema_dir()
        version_schemafile = os.path.join(
            schema_dir, VERSIONED_USERDATA_SCHEMA_FILE
        )
        # Point to local schema files avoid JSON resolver trying to pull the
        # reference from our upstream raw file in github.
        version_schema = json.loads(
            re.sub(
                r"https:\/\/raw.githubusercontent.com\/canonical\/"
                r"cloud-init\/main\/cloudinit\/config\/schemas\/",
                f"file://{schema_dir}/",
                load_file(version_schemafile),
            )
        )
        if error_msg:
            with pytest.raises(SchemaValidationError) as context_mgr:
                validate_cloudconfig_schema(
                    schema, schema=version_schema, strict=True
                )
            assert error_msg in str(context_mgr.value)
        else:
            validate_cloudconfig_schema(
                schema, schema=version_schema, strict=True
            )


class TestGetSchema:
    def test_static_schema_file_is_valid(self, caplog):
        with caplog.at_level(logging.WARNING):
            get_schema()
        # Assert no warnings parsing our packaged schema file
        warnings = [msg for (_, _, msg) in caplog.record_tuples]
        assert [] == warnings

    def test_get_schema_coalesces_known_schema(self):
        """Every cloudconfig module with schema is listed in allOf keyword."""
        schema = get_schema()
        assert sorted(get_module_names()) == sorted(
            [meta["id"] for meta in get_metas().values() if meta is not None]
        )
        assert "http://json-schema.org/draft-04/schema#" == schema["$schema"]
        assert ["$defs", "$schema", "allOf"] == sorted(list(schema.keys()))
        # New style schema should be defined in static schema file in $defs
        expected_subschema_defs = [
            {"$ref": "#/$defs/base_config"},
            {"$ref": "#/$defs/cc_ansible"},
            {"$ref": "#/$defs/cc_apk_configure"},
            {"$ref": "#/$defs/cc_apt_configure"},
            {"$ref": "#/$defs/cc_apt_pipelining"},
            {"$ref": "#/$defs/cc_ubuntu_autoinstall"},
            {"$ref": "#/$defs/cc_bootcmd"},
            {"$ref": "#/$defs/cc_byobu"},
            {"$ref": "#/$defs/cc_ca_certs"},
            {"$ref": "#/$defs/cc_chef"},
            {"$ref": "#/$defs/cc_disable_ec2_metadata"},
            {"$ref": "#/$defs/cc_disk_setup"},
            {"$ref": "#/$defs/cc_fan"},
            {"$ref": "#/$defs/cc_final_message"},
            {"$ref": "#/$defs/cc_growpart"},
            {"$ref": "#/$defs/cc_grub_dpkg"},
            {"$ref": "#/$defs/cc_install_hotplug"},
            {"$ref": "#/$defs/cc_keyboard"},
            {"$ref": "#/$defs/cc_keys_to_console"},
            {"$ref": "#/$defs/cc_landscape"},
            {"$ref": "#/$defs/cc_locale"},
            {"$ref": "#/$defs/cc_lxd"},
            {"$ref": "#/$defs/cc_mcollective"},
            {"$ref": "#/$defs/cc_migrator"},
            {"$ref": "#/$defs/cc_mounts"},
            {"$ref": "#/$defs/cc_ntp"},
            {"$ref": "#/$defs/cc_package_update_upgrade_install"},
            {"$ref": "#/$defs/cc_phone_home"},
            {"$ref": "#/$defs/cc_power_state_change"},
            {"$ref": "#/$defs/cc_puppet"},
            {"$ref": "#/$defs/cc_resizefs"},
            {"$ref": "#/$defs/cc_resolv_conf"},
            {"$ref": "#/$defs/cc_rh_subscription"},
            {"$ref": "#/$defs/cc_rsyslog"},
            {"$ref": "#/$defs/cc_runcmd"},
            {"$ref": "#/$defs/cc_salt_minion"},
            {"$ref": "#/$defs/cc_scripts_vendor"},
            {"$ref": "#/$defs/cc_seed_random"},
            {"$ref": "#/$defs/cc_set_hostname"},
            {"$ref": "#/$defs/cc_set_passwords"},
            {"$ref": "#/$defs/cc_snap"},
            {"$ref": "#/$defs/cc_spacewalk"},
            {"$ref": "#/$defs/cc_ssh_authkey_fingerprints"},
            {"$ref": "#/$defs/cc_ssh_import_id"},
            {"$ref": "#/$defs/cc_ssh"},
            {"$ref": "#/$defs/cc_timezone"},
            {"$ref": "#/$defs/cc_ubuntu_advantage"},
            {"$ref": "#/$defs/cc_ubuntu_drivers"},
            {"$ref": "#/$defs/cc_update_etc_hosts"},
            {"$ref": "#/$defs/cc_update_hostname"},
            {"$ref": "#/$defs/cc_users_groups"},
            {"$ref": "#/$defs/cc_wireguard"},
            {"$ref": "#/$defs/cc_write_files"},
            {"$ref": "#/$defs/cc_yum_add_repo"},
            {"$ref": "#/$defs/cc_zypper_add_repo"},
            {"$ref": "#/$defs/reporting_config"},
        ]
        found_subschema_defs = []
        legacy_schema_keys = []
        for subschema in schema["allOf"]:
            if "$ref" in subschema:
                found_subschema_defs.append(subschema)
            else:  # Legacy subschema sourced from cc_* module 'schema' attr
                legacy_schema_keys.extend(subschema["properties"].keys())

        assert expected_subschema_defs == found_subschema_defs
        # This list should remain empty unless we induct new modules with
        # legacy schema attributes defined within the cc_module.
        assert [] == sorted(legacy_schema_keys)


class TestLoadDoc:

    docs = get_module_variable("__doc__")

    @pytest.mark.parametrize(
        "module_name",
        ("cc_apt_pipelining",),  # new style composite schema file
    )
    def test_report_docs_consolidated_schema(self, module_name):
        doc = load_doc([module_name])
        assert doc, "Unexpected empty docs for {}".format(module_name)
        assert self.docs[module_name] == doc


class SchemaValidationErrorTest(CiTestCase):
    """Test validate_cloudconfig_schema"""

    def test_schema_validation_error_expects_schema_errors(self):
        """SchemaValidationError is initialized from schema_errors."""
        errors = [
            SchemaProblem("key.path", 'unexpected key "junk"'),
            SchemaProblem(
                "key2.path", '"-123" is not a valid "hostname" format'
            ),
        ]
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
    def test_validateconfig_schema_sensitive(self, caplog):
        """When log_details=False, ensure details are omitted"""
        schema = {
            "properties": {"hashed_password": {"type": "string"}},
            "additionalProperties": False,
        }
        validate_cloudconfig_schema(
            {"hashed-password": "secret"},
            schema,
            strict=False,
            log_details=False,
        )
        [(module, log_level, log_msg)] = caplog.record_tuples
        assert "cloudinit.config.schema" == module
        assert logging.WARNING == log_level
        assert (
            "Invalid cloud-config provided: Please run 'sudo cloud-init "
            "schema --system' to see the schema errors." == log_msg
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

    @skipUnlessJsonSchema()
    @pytest.mark.parametrize("log_deprecations", [True, False])
    @pytest.mark.parametrize(
        "schema,config,expected_msg",
        [
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "a-b": {
                            "type": "string",
                            "deprecated": True,
                            "description": "<desc>",
                        },
                        "a_b": {"type": "string", "description": "noop"},
                    },
                },
                {"a-b": "asdf"},
                "Deprecated cloud-config provided:\na-b: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "x": {
                            "oneOf": [
                                {"type": "integer", "description": "noop"},
                                {
                                    "type": "string",
                                    "deprecated": True,
                                    "description": "<desc>",
                                },
                            ]
                        },
                    },
                },
                {"x": "+5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "x": {
                            "allOf": [
                                {"type": "string", "description": "noop"},
                                {
                                    "deprecated": True,
                                    "description": "<desc>",
                                },
                            ]
                        },
                    },
                },
                {"x": "5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "x": {
                            "anyOf": [
                                {"type": "integer", "description": "noop"},
                                {
                                    "type": "string",
                                    "deprecated": True,
                                    "description": "<desc>",
                                },
                            ]
                        },
                    },
                },
                {"x": "5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "x": {
                            "type": "string",
                            "deprecated": True,
                            "description": "<desc>",
                        },
                    },
                },
                {"x": "+5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "x": {
                            "type": "string",
                            "deprecated": False,
                            "description": "<desc>",
                        },
                    },
                },
                {"x": "+5"},
                None,
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "$defs": {
                        "my_ref": {
                            "deprecated": True,
                            "description": "<desc>",
                        }
                    },
                    "properties": {
                        "x": {
                            "allOf": [
                                {"type": "string", "description": "noop"},
                                {"$ref": "#/$defs/my_ref"},
                            ]
                        },
                    },
                },
                {"x": "+5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED: <desc>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "$defs": {
                        "my_ref": {
                            "deprecated": True,
                        }
                    },
                    "properties": {
                        "x": {
                            "allOf": [
                                {
                                    "type": "string",
                                    "description": "noop",
                                },
                                {"$ref": "#/$defs/my_ref"},
                            ]
                        },
                    },
                },
                {"x": "+5"},
                "Deprecated cloud-config provided:\nx: DEPRECATED.",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "patternProperties": {
                        "^.+$": {
                            "minItems": 1,
                            "deprecated": True,
                            "description": "<desc>",
                        }
                    },
                },
                {"a-b": "asdf"},
                "Deprecated cloud-config provided:\na-b: DEPRECATED: <desc>",
            ),
            pytest.param(
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "patternProperties": {
                        "^.+$": {
                            "minItems": 1,
                            "deprecated": True,
                        }
                    },
                },
                {"a-b": "asdf"},
                "Deprecated cloud-config provided:\na-b: DEPRECATED.",
                id="deprecated_pattern_property_without_description",
            ),
        ],
    )
    def test_validateconfig_logs_deprecations(
        self, schema, config, expected_msg, log_deprecations, caplog
    ):
        validate_cloudconfig_schema(
            config,
            schema,
            strict_metaschema=True,
            log_deprecations=log_deprecations,
        )
        if expected_msg is None:
            return
        log_record = (M_PATH[:-1], logging.WARNING, expected_msg)
        if log_deprecations:
            assert log_record == caplog.record_tuples[-1]
        else:
            assert log_record not in caplog.record_tuples


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
        config_load = load(example)
        # cloud-init-schema-v1 is permissive of additionalProperties at the
        # top-level.
        # To validate specific schemas against known documented examples
        # we need to only define the specific module schema and supply
        # strict=True.
        # TODO(Drop to pop/update once full schema is strict)
        schema.pop("allOf")
        schema.update(schema["$defs"][schema_id])
        schema["additionalProperties"] = False
        # Some module examples reference keys defined in multiple schemas
        supplemental_schemas = {
            "cc_ubuntu_advantage": ["cc_power_state_change"],
            "cc_update_hostname": ["cc_set_hostname"],
            "cc_users_groups": ["cc_ssh_import_id"],
            "cc_disk_setup": ["cc_mounts"],
        }
        for supplement_id in supplemental_schemas.get(schema_id, []):
            supplemental_props = dict(
                [
                    (key, value)
                    for key, value in schema["$defs"][supplement_id][
                        "properties"
                    ].items()
                ]
            )
            schema["properties"].update(supplemental_props)
        validate_cloudconfig_schema(config_load, schema, strict=True)


@pytest.mark.usefixtures("fake_filesystem")
class TestValidateCloudConfigFile:
    """Tests for validate_cloudconfig_file."""

    @pytest.mark.parametrize("annotate", (True, False))
    def test_validateconfig_file_error_on_absent_file(self, annotate):
        """On absent config_path, validate_cloudconfig_file errors."""
        with pytest.raises(
            RuntimeError, match="Configfile /not/here does not exist"
        ):
            validate_cloudconfig_file("/not/here", {}, annotate)

    @pytest.mark.parametrize("annotate", (True, False))
    def test_validateconfig_file_error_on_invalid_header(
        self, annotate, tmpdir
    ):
        """On invalid header, validate_cloudconfig_file errors.

        A SchemaValidationError is raised when the file doesn't begin with
        CLOUD_CONFIG_HEADER.
        """
        config_file = tmpdir.join("my.yaml")
        config_file.write("#junk")
        error_msg = (
            "Cloud config schema errors: format-l1.c1: File"
            f" {config_file} needs to begin with"
            f' "{CLOUD_CONFIG_HEADER.decode()}"'
        )
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_file(config_file.strpath, {}, annotate)

    @pytest.mark.parametrize("annotate", (True, False))
    def test_validateconfig_file_error_on_non_yaml_scanner_error(
        self, annotate, tmpdir
    ):
        """On non-yaml scan issues, validate_cloudconfig_file errors."""
        # Generate a scanner error by providing text on a single line with
        # improper indent.
        config_file = tmpdir.join("my.yaml")
        config_file.write("#cloud-config\nasdf:\nasdf")
        error_msg = (
            f".*errors: format-l3.c1: File {config_file} is not valid yaml.*"
        )
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_file(config_file.strpath, {}, annotate)

    @pytest.mark.parametrize("annotate", (True, False))
    def test_validateconfig_file_error_on_non_yaml_parser_error(
        self, annotate, tmpdir
    ):
        """On non-yaml parser issues, validate_cloudconfig_file errors."""
        config_file = tmpdir.join("my.yaml")
        config_file.write("#cloud-config\n{}}")
        error_msg = (
            f"errors: format-l2.c3: File {config_file} is not valid yaml."
        )
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_file(config_file.strpath, {}, annotate)

    @skipUnlessJsonSchema()
    @pytest.mark.parametrize("annotate", (True, False))
    def test_validateconfig_file_strictly_validates_schema(
        self, annotate, tmpdir
    ):
        """validate_cloudconfig_file raises errors on invalid schema."""
        config_file = tmpdir.join("my.yaml")
        schema = {"properties": {"p1": {"type": "string", "format": "string"}}}
        config_file.write("#cloud-config\np1: -1")
        error_msg = (
            "Cloud config schema errors: p1: -1 is not of type 'string'"
        )
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_file(config_file.strpath, schema, annotate)

    @skipUnlessJsonSchema()
    @responses.activate
    @pytest.mark.parametrize("annotate", (True, False))
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch(M_PATH + "os.getuid", return_value=0)
    def test_validateconfig_file_include_validates_schema(
        self, m_getuid, m_sleep, annotate, mocker
    ):
        """validate_cloudconfig_file raises errors on invalid schema
        when user-data uses `#include`."""
        schema = {"properties": {"p1": {"type": "string", "format": "string"}}}
        included_data = "#cloud-config\np1: -1"
        included_url = "http://asdf/user-data"
        blob = f"#include {included_url}"
        responses.add(responses.GET, included_url, included_data)

        ci = stages.Init()
        ci.datasource = FakeDataSource(blob)
        mocker.patch(M_PATH + "Init", return_value=ci)

        error_msg = (
            "Cloud config schema errors: p1: -1 is not of type 'string'"
        )
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_file(None, schema, annotate)

    @skipUnlessJsonSchema()
    @responses.activate
    @pytest.mark.parametrize("annotate", (True, False))
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch(M_PATH + "os.getuid", return_value=0)
    def test_validateconfig_file_include_success(
        self, m_getuid, m_sleep, annotate, mocker
    ):
        """validate_cloudconfig_file raises errors on invalid schema
        when user-data uses `#include`."""
        schema = {"properties": {"p1": {"type": "string", "format": "string"}}}
        included_data = "#cloud-config\np1: asdf"
        included_url = "http://asdf/user-data"
        blob = f"#include {included_url}"
        responses.add(responses.GET, included_url, included_data)

        ci = stages.Init()
        ci.datasource = FakeDataSource(blob)
        mocker.patch(M_PATH + "Init", return_value=ci)

        validate_cloudconfig_file(None, schema, annotate)

    @skipUnlessJsonSchema()
    @pytest.mark.parametrize("annotate", (True, False))
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch(M_PATH + "os.getuid", return_value=0)
    def test_validateconfig_file_no_cloud_cfg(
        self, m_getuid, m_sleep, annotate, capsys, mocker
    ):
        """validate_cloudconfig_file does noop with empty user-data."""
        schema = {"properties": {"p1": {"type": "string", "format": "string"}}}
        blob = ""

        ci = stages.Init()
        ci.datasource = FakeDataSource(blob)
        mocker.patch(M_PATH + "Init", return_value=ci)

        with pytest.raises(
            SchemaValidationError,
            match=re.escape(
                "Cloud config schema errors: format-l1.c1: File None needs"
                ' to begin with "#cloud-config"'
            ),
        ):
            validate_cloudconfig_file(None, schema, annotate)


class TestSchemaDocMarkdown:
    """Tests for get_meta_doc."""

    required_schema = {
        "title": "title",
        "description": "description",
        "id": "id",
        "name": "name",
        "frequency": "frequency",
        "distros": ["debian", "rhel"],
    }
    meta: MetaSchema = {
        "title": "title",
        "description": "description",
        "id": "id",
        "name": "name",
        "frequency": "frequency",
        "distros": ["debian", "rhel"],
        "examples": [
            'prop1:\n    [don\'t, expand, "this"]',
            "prop2: true",
        ],
    }

    @pytest.mark.parametrize(
        "meta_update",
        [
            None,
            {"activate_by_schema_keys": None},
            {"activate_by_schema_keys": []},
        ],
    )
    def test_get_meta_doc_returns_restructured_text(self, meta_update):
        """get_meta_doc returns restructured text for a cloudinit schema."""
        full_schema = deepcopy(self.required_schema)
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
        meta = deepcopy(self.meta)
        if meta_update:
            meta.update(meta_update)

        doc = get_meta_doc(meta, full_schema)
        assert (
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
                **prop1:** (array of integer) prop-description.

            **Examples**::

                prop1:
                    [don't, expand, "this"]
                # --- Example2 ---
                prop2: true
        """
            )
            == doc
        )

    def test_get_meta_doc_full_with_activate_by_schema_keys(self):
        full_schema = deepcopy(self.required_schema)
        full_schema.update(
            {
                "properties": {
                    "prop1": {
                        "type": "array",
                        "description": "prop-description",
                        "items": {"type": "string"},
                    },
                    "prop2": {
                        "type": "boolean",
                        "description": "prop2-description",
                    },
                },
            }
        )

        meta = deepcopy(self.meta)
        meta["activate_by_schema_keys"] = ["prop1", "prop2"]

        doc = get_meta_doc(meta, full_schema)
        assert (
            dedent(
                """
            name
            ----
            **Summary:** title

            description

            **Internal name:** ``id``

            **Module frequency:** frequency

            **Supported distros:** debian, rhel

            **Activate only on keys:** ``prop1``, ``prop2``

            **Config schema**:
                **prop1:** (array of string) prop-description.

                **prop2:** (boolean) prop2-description.

            **Examples**::

                prop1:
                    [don't, expand, "this"]
                # --- Example2 ---
                prop2: true
        """
            )
            == doc
        )

    def test_get_meta_doc_handles_multiple_types(self):
        """get_meta_doc delimits multiple property types with a '/'."""
        schema = {"properties": {"prop1": {"type": ["string", "integer"]}}}
        assert "**prop1:** (string/integer)" in get_meta_doc(self.meta, schema)

    @pytest.mark.parametrize("multi_key", ["oneOf", "anyOf"])
    def test_get_meta_doc_handles_multiple_types_recursive(self, multi_key):
        """get_meta_doc delimits multiple property types with a '/'."""
        schema = {
            "properties": {
                "prop1": {
                    multi_key: [
                        {"type": ["string", "null"]},
                        {"type": "integer"},
                    ]
                }
            }
        }
        assert "**prop1:** (string/null/integer)" in get_meta_doc(
            self.meta, schema
        )

    def test_references_are_flattened_in_schema_docs(self):
        """get_meta_doc flattens and renders full schema definitions."""
        schema = {
            "$defs": {
                "flattenit": {
                    "type": ["object", "string"],
                    "description": "Objects support the following keys:",
                    "patternProperties": {
                        "^.+$": {
                            "label": "<opaque_label>",
                            "description": "List of cool strings",
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        }
                    },
                }
            },
            "properties": {"prop1": {"$ref": "#/$defs/flattenit"}},
        }
        assert (
            dedent(
                """\
            **prop1:** (string/object) Objects support the following keys:

                    **<opaque_label>:** (array of string) List of cool strings.
            """
            )
            in get_meta_doc(self.meta, schema)
        )

    @pytest.mark.parametrize(
        "sub_schema,expected",
        (
            (
                {"enum": [True, False, "stuff"]},
                "**prop1:** (``true``/``false``/``stuff``)",
            ),
            # When type: string and enum, document enum values
            (
                {"type": "string", "enum": ["a", "b"]},
                "**prop1:** (``a``/``b``)",
            ),
        ),
    )
    def test_get_meta_doc_handles_enum_types(self, sub_schema, expected):
        """get_meta_doc converts enum types to yaml and delimits with '/'."""
        schema = {"properties": {"prop1": sub_schema}}
        assert expected in get_meta_doc(self.meta, schema)

    @pytest.mark.parametrize(
        "schema,expected",
        (
            (  # Hide top-level keys like 'properties'
                {
                    "hidden": ["properties"],
                    "properties": {
                        "p1": {"type": "string"},
                        "p2": {"type": "boolean"},
                    },
                    "patternProperties": {
                        "^.*$": {
                            "type": "string",
                            "label": "label2",
                        }
                    },
                },
                dedent(
                    """
                **Config schema**:
                    **label2:** (string)
                """
                ),
            ),
            (  # Hide nested individual keys with a bool
                {
                    "properties": {
                        "p1": {"type": "string", "hidden": True},
                        "p2": {"type": "boolean"},
                    }
                },
                dedent(
                    """
                **Config schema**:
                    **p2:** (boolean)
                """
                ),
            ),
        ),
    )
    def test_get_meta_doc_hidden_hides_specific_properties_from_docs(
        self, schema, expected
    ):
        """Docs are hidden for any property in the hidden list.

        Useful for hiding deprecated key schema.
        """
        assert expected in get_meta_doc(self.meta, schema)

    @pytest.mark.parametrize("multi_key", ["oneOf", "anyOf"])
    def test_get_meta_doc_handles_nested_multi_schema_property_types(
        self, multi_key
    ):
        """get_meta_doc describes array items oneOf declarations in type."""
        schema = {
            "properties": {
                "prop1": {
                    "type": "array",
                    "items": {
                        multi_key: [{"type": "string"}, {"type": "integer"}]
                    },
                }
            }
        }
        assert "**prop1:** (array of (string/integer))" in get_meta_doc(
            self.meta, schema
        )

    @pytest.mark.parametrize("multi_key", ["oneOf", "anyOf"])
    def test_get_meta_doc_handles_types_as_list(self, multi_key):
        """get_meta_doc renders types which have a list value."""
        schema = {
            "properties": {
                "prop1": {
                    "type": ["boolean", "array"],
                    "items": {
                        multi_key: [{"type": "string"}, {"type": "integer"}]
                    },
                }
            }
        }
        assert (
            "**prop1:** (boolean/array of (string/integer))"
            in get_meta_doc(self.meta, schema)
        )

    def test_get_meta_doc_handles_flattening_defs(self):
        """get_meta_doc renders $defs."""
        schema = {
            "$defs": {
                "prop1object": {
                    "type": "object",
                    "properties": {"subprop": {"type": "string"}},
                }
            },
            "properties": {"prop1": {"$ref": "#/$defs/prop1object"}},
        }
        assert (
            "**prop1:** (object)\n\n        **subprop:** (string)\n"
            in get_meta_doc(self.meta, schema)
        )

    def test_get_meta_doc_handles_string_examples(self):
        """get_meta_doc properly indented examples as a list of strings."""
        full_schema = deepcopy(self.required_schema)
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
        assert (
            dedent(
                """
            **Config schema**:
                **prop1:** (array of integer) prop-description.

            **Examples**::

                prop1:
                    [don't, expand, "this"]
                # --- Example2 ---
                prop2: true
            """
            )
            in get_meta_doc(self.meta, full_schema)
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

        assert (
            dedent(
                """
            **Config schema**:
                **p1:** (string) This item has the following options:

                        - option1
                        - option2
                        - option3

                The default value is option1.

        """
            )
            in get_meta_doc(self.meta, schema)
        )

    @pytest.mark.parametrize("key", meta.keys())
    def test_get_meta_doc_raises_key_errors(self, key):
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
        invalid_meta = deepcopy(self.meta)
        invalid_meta.pop(key)
        with pytest.raises(
            KeyError,
            match=f"Missing required keys in module meta: {{'{key}'}}",
        ):
            get_meta_doc(invalid_meta, schema)

    @pytest.mark.parametrize(
        "key,expectation",
        [
            ("activate_by_schema_keys", does_not_raise()),
            (
                "additional_key",
                pytest.raises(
                    KeyError,
                    match=(
                        "Additional unexpected keys found in module meta:"
                        " {'additional_key'}"
                    ),
                ),
            ),
        ],
    )
    def test_get_meta_doc_additional_keys(self, key, expectation):
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
        invalid_meta = deepcopy(self.meta)
        invalid_meta[key] = []
        with expectation:
            get_meta_doc(invalid_meta, schema)

    def test_label_overrides_property_name(self):
        """get_meta_doc overrides property name with label."""
        schema = {
            "properties": {
                "old_prop1": {
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
        assert "Each object in **array_label** list" in meta_doc

        assert "old_prop1" not in meta_doc
        assert ".*" not in meta_doc

    @pytest.mark.parametrize(
        "schema,expected_doc",
        [
            (
                {
                    "properties": {
                        "prop1": {
                            "type": ["string", "integer"],
                            "deprecated": True,
                            "description": "<description>",
                        }
                    }
                },
                "**prop1:** (string/integer) DEPRECATED: <description>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "prop1": {
                            "type": ["string", "integer"],
                            "description": "<description>",
                            "deprecated": True,
                        },
                    },
                },
                "**prop1:** (string/integer) DEPRECATED: <description>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "$defs": {"my_ref": {"deprecated": True}},
                    "properties": {
                        "prop1": {
                            "allOf": [
                                {
                                    "type": ["string", "integer"],
                                    "description": "<description>",
                                },
                                {"$ref": "#/$defs/my_ref"},
                            ]
                        }
                    },
                },
                "**prop1:** (string/integer) DEPRECATED: <description>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "$defs": {
                        "my_ref": {
                            "deprecated": True,
                            "description": "<description>",
                        }
                    },
                    "properties": {
                        "prop1": {
                            "allOf": [
                                {"type": ["string", "integer"]},
                                {"$ref": "#/$defs/my_ref"},
                            ]
                        }
                    },
                },
                "**prop1:** (string/integer) DEPRECATED: <description>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "prop1": {
                            "description": "<description>",
                            "anyOf": [
                                {
                                    "type": ["string", "integer"],
                                    "description": "<deprecated_description>",
                                    "deprecated": True,
                                },
                            ],
                        },
                    },
                },
                "**prop1:** (UNDEFINED) <description>. DEPRECATED: <deprecat",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "prop1": {
                            "anyOf": [
                                {
                                    "type": ["string", "integer"],
                                    "description": "<deprecated_description>",
                                    "deprecated": True,
                                },
                                {
                                    "type": "number",
                                    "description": "<description>",
                                },
                            ]
                        },
                    },
                },
                "**prop1:** (number) <description>. DEPRECATED:"
                " <deprecated_description>",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "prop1": {
                            "anyOf": [
                                {
                                    "type": ["string", "integer"],
                                    "description": "<deprecated_description>",
                                    "deprecated": True,
                                },
                                {
                                    "type": "string",
                                    "enum": ["none", "unchanged", "os"],
                                    "description": "<description>",
                                },
                            ]
                        },
                    },
                },
                "**prop1:** (``none``/``unchanged``/``os``) <description>."
                " DEPRECATED: <deprecated_description>.",
            ),
            (
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "properties": {
                        "prop1": {
                            "anyOf": [
                                {
                                    "type": ["string", "integer"],
                                    "description": "<description_1>",
                                },
                                {
                                    "type": "string",
                                    "enum": ["none", "unchanged", "os"],
                                    "description": "<description>_2",
                                },
                            ]
                        },
                    },
                },
                "**prop1:** (string/integer/``none``/``unchanged``/``os``)"
                " <description_1>. <description>_2.\n",
            ),
            (
                {
                    "properties": {
                        "prop1": {
                            "description": "<desc_1>",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "anyOf": [
                                    {
                                        "properties": {
                                            "sub_prop1": {"type": "string"},
                                        },
                                    },
                                ],
                            },
                        },
                    },
                },
                "**prop1:** (array of object) <desc_1>.\n",
            ),
        ],
    )
    def test_get_meta_doc_render_deprecated_info(self, schema, expected_doc):
        assert expected_doc in get_meta_doc(self.meta, schema)


class TestAnnotatedCloudconfigFile:
    def test_annotated_cloudconfig_file_no_schema_errors(self):
        """With no schema_errors, print the original content."""
        content = b"ntp:\n  pools: [ntp1.pools.com]\n"
        parse_cfg, schemamarks = load_with_marks(content)
        assert content == annotated_cloudconfig_file(
            parse_cfg,
            content,
            schemamarks=schemamarks,
            schema_errors=[],
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
        assert expected == annotated_cloudconfig_file(
            None,
            content,
            schemamarks={},
            schema_errors=[SchemaProblem("", "None is not of type 'object'")],
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
        parsed_config, schemamarks = load_with_marks(content[13:])
        schema_errors = [
            SchemaProblem("ntp", "Some type error"),
            SchemaProblem("ntp.pools.0", "-99 is not a string"),
            SchemaProblem("ntp.pools.1", "75 is not a string"),
        ]
        assert expected == annotated_cloudconfig_file(
            parsed_config,
            content,
            schemamarks=schemamarks,
            schema_errors=schema_errors,
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
        parsed_config, schemamarks = load_with_marks(content[13:])
        schema_errors = [
            SchemaProblem("ntp.pools.0", "-99 is not a string"),
            SchemaProblem("ntp.pools.1", "75 is not a string"),
        ]
        assert expected in annotated_cloudconfig_file(
            parsed_config,
            content,
            schemamarks=schemamarks,
            schema_errors=schema_errors,
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

    @mock.patch(M_PATH + "os.getuid", return_value=0)
    def test_main_validates_system_userdata(
        self, m_getuid, capsys, mocker, paths
    ):
        """When --system is provided, main validates system userdata."""
        m_init = mocker.patch(M_PATH + "Init")
        m_init.return_value.paths.get_ipath = paths.get_ipath_cur
        cloud_config_file = paths.get_ipath_cur("cloud_config")
        write_file(cloud_config_file, b"#cloud-config\nntp:")
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


class TestMeta:
    def test_valid_meta_for_every_module(self):
        all_distros = {
            name for distro in OSFAMILIES.values() for name in distro
        }
        all_distros.add("all")
        for module in get_modules():
            assert "frequency" in module.meta
            assert "distros" in module.meta
            assert {module.meta["frequency"]}.issubset(FREQUENCIES)
            assert set(module.meta["distros"]).issubset(all_distros)


def remove_modules(schema, modules: Set[str]) -> dict:
    indices_to_delete = set()
    for module in set(modules):
        for index, ref_dict in enumerate(schema["allOf"]):
            if ref_dict["$ref"] == f"#/$defs/{module}":
                indices_to_delete.add(index)
                continue  # module found
    for index in indices_to_delete:
        schema["allOf"].pop(index)
    return schema


def remove_defs(schema, defs: Set[str]) -> dict:
    defs_to_delete = set(schema["$defs"].keys()).intersection(set(defs))
    for key in defs_to_delete:
        del schema["$defs"][key]
    return schema


def clean_schema(
    schema=None,
    modules: Optional[Sequence[str]] = None,
    defs: Optional[Sequence[str]] = None,
):
    schema = deepcopy(schema or get_schema())
    if modules:
        remove_modules(schema, set(modules))
    if defs:
        remove_defs(schema, set(defs))
    return schema


@pytest.mark.hypothesis_slow
class TestSchemaFuzz:

    # Avoid https://github.com/Zac-HD/hypothesis-jsonschema/issues/97
    SCHEMA = clean_schema(
        modules=["cc_users_groups"],
        defs=["users_groups.groups_by_groupname", "users_groups.user"],
    )

    @skipUnlessHypothesisJsonSchema()
    @given(from_schema(SCHEMA))
    def test_validate_full_schema(self, config):
        try:
            validate_cloudconfig_schema(config, strict=True)
        except SchemaValidationError as ex:
            if ex.has_errors():
                raise


class TestHandleSchemaArgs:

    Args = namedtuple("Args", "config_file docs system annotate")

    @pytest.mark.parametrize(
        "annotate, expected_output",
        [
            (
                True,
                dedent(
                    """\
                    #cloud-config
                    packages:
                    - htop
                    apt_update: true		# D1
                    apt_upgrade: true		# D2
                    apt_reboot_if_required: true		# D3

                    # Deprecations: -------------
                    # D1: DEPRECATED: Dropped after April 2027. Use ``package_update``. Default: ``false``
                    # D2: DEPRECATED: Dropped after April 2027. Use ``package_upgrade``. Default: ``false``
                    # D3: DEPRECATED: Dropped after April 2027. Use ``package_reboot_if_required``. Default: ``false``


                    Valid cloud-config: {}
                    """  # noqa: E501
                ),
            ),
            (
                False,
                dedent(
                    """\
                    Cloud config schema deprecations: \
apt_reboot_if_required: DEPRECATED: Dropped after April 2027. Use ``package_reboot_if_required``. Default: ``false``, \
apt_update: DEPRECATED: Dropped after April 2027. Use ``package_update``. Default: ``false``, \
apt_upgrade: DEPRECATED: Dropped after April 2027. Use ``package_upgrade``. Default: ``false``
                    Valid cloud-config: {}
                    """  # noqa: E501
                ),
            ),
        ],
    )
    def test_handle_schema_args_annotate_deprecated_config(
        self, annotate, expected_output, caplog, capsys, tmpdir
    ):
        user_data_fn = tmpdir.join("user-data")
        with open(user_data_fn, "w") as f:
            f.write(
                dedent(
                    """\
                    #cloud-config
                    packages:
                    - htop
                    apt_update: true
                    apt_upgrade: true
                    apt_reboot_if_required: true
                    """
                )
            )
        args = self.Args(
            config_file=str(user_data_fn),
            annotate=annotate,
            docs=None,
            system=None,
        )
        handle_schema_args("unused", args)
        out, err = capsys.readouterr()
        assert expected_output.format(user_data_fn) == out
        assert not err
        assert "deprec" not in caplog.text
