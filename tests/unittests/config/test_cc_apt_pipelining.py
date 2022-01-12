# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_apt_pipelining handler"""

from pathlib import Path

import pytest

import cloudinit.config.cc_apt_pipelining as cc_apt_pipelining
from cloudinit import util
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    cloud_init_project_dir,
    mock,
    skipUnlessJsonSchema,
)


class TestAptPipelining:
    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_not_disabled_by_default(self, m_write_file):
        """ensure that default behaviour is to not disable pipelining"""
        cc_apt_pipelining.handle("foo", {}, None, mock.MagicMock(), None)
        assert 0 == m_write_file.call_count

    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_false_disables_pipelining(self, m_write_file):
        """ensure that pipelining can be disabled with correct config"""
        cc_apt_pipelining.handle(
            "foo", {"apt_pipelining": "false"}, None, mock.MagicMock(), None
        )
        assert 1 == m_write_file.call_count
        args, _ = m_write_file.call_args
        assert cc_apt_pipelining.DEFAULT_FILE == args[0]
        assert 'Pipeline-Depth "0"' in args[1]

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas
            ({}, None),
            ({"apt_pipelining": 1}, None),
            ({"apt_pipelining": True}, None),
            ({"apt_pipelining": False}, None),
            ({"apt_pipelining": "none"}, None),
            ({"apt_pipelining": "unchanged"}, None),
            ({"apt_pipelining": "os"}, None),
            # Invalid schemas
            (
                {"apt_pipelining": "bogus"},
                "Cloud config schema errors: apt_pipelining: 'bogus' is not"
                " valid under any of the given schema",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    @mock.patch("cloudinit.config.schema.read_cfg_paths")
    def test_schema_validation(self, read_cfg_paths, config, error_msg, paths):
        """Assert expected schema validation and error messages."""
        read_cfg_paths.return_value = paths
        # New-style schema $defs exist in config/cloud-init-schema*.json
        for schema_file in Path(cloud_init_project_dir("config/")).glob(
            "cloud-init-schema*.json"
        ):
            util.copy(schema_file, paths.schema_dir)
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)


# vi: ts=4 expandtab
