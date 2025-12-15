# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cc_write_metadata module."""

import logging
from unittest import mock

import pytest

from cloudinit.config import cc_write_metadata
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)
M_PATH = "cloudinit.config.cc_write_metadata."


@pytest.fixture
def cloud():
    """Fixture to provide a mock cloud object with datasource."""
    cl = get_cloud()
    cl.datasource = mock.Mock()
    cl.datasource.metadata = {
        "instance-id": "i-1234567890abcdef0",
        "region": "us-east-1",
        "availability-zone": "us-east-1a",
        "instance-type": "",
    }
    cl.datasource.identity = {
        "region": "us-east-1",
        "account-id": "123456789012",
    }
    return cl


class TestRetrieveMetadata:
    """Tests for retrieve_metadata function."""

    @pytest.mark.parametrize(
        "data,expected_result",
        [
            (["no-instance-id"], "no-instance-id"),
            ([{"metadata": "instance-id"}], "i-1234567890abcdef0"),
            ([{"metadata": "region"}], "us-east-1"),
            ([{"metadata": "availability-zone"}], "us-east-1a"),
            ([{"identity": "region"}], "us-east-1"),
            ([{"identity": "account-id"}], "123456789012"),
            ([{"metadata": "public-ipv4"}, "unknown-ip"], "unknown-ip"),
            ([{"metadata": "instance-type", "allowempty": True}], ""),
            ([{"metadata": "public-ipv4"}], None),
        ],
    )
    def test_retrieve_metadata(
        self, cloud, data, expected_result
    ):
        """Test metadata retrieval from various sources with fallbacks."""
        result = cc_write_metadata.retrieve_metadata("/", data, cloud)
        assert expected_result == result

    def test_handles_missing_dataset_attribute(self, cloud):
        """Warn and continue when datasource doesn't have the dataset."""
        delattr(cloud.datasource, "metadata")
        data = [{"metadata": "instance-id"}, "no-instance-id"]
        result = cc_write_metadata.retrieve_metadata("/", data, cloud)
        assert "no-instance-id" == result

    def test_multiple_fallback_attempts(self, cloud):
        """Try multiple metadata sources before using string fallback."""
        data = [
            {"metadata": "public-ipv4"},
            {"metadata": "public-hostname"},
            {"metadata": "instance-id"},
        ]
        result = cc_write_metadata.retrieve_metadata("/", data, cloud)
        assert "i-1234567890abcdef0" == result


class TestWriteMetadata:
    """Tests for write_metadata function."""

    @pytest.mark.parametrize(
        "files,expected_warning",
        [
            (
                [{"data": [{"metadata": "instance-id"}]}],
                "No path provided",
            ),
            (
                [{"path": "/var/lib/cloud/instance/metadata"}],
                "No data provided",
            ),
        ],
    )
    @mock.patch(M_PATH + "cc_write_files.write_files")
    def test_skips_invalid_entries(
        self, m_write_files, cloud, caplog, files, expected_warning
    ):
        """Warn and skip entries with missing required fields."""
        cc_write_metadata.write_metadata("cc_write_metadata", files, cloud)
        assert expected_warning in caplog.text
        assert 1 == m_write_files.call_count

    @mock.patch(M_PATH + "cc_write_files.write_files")
    @mock.patch(M_PATH + "retrieve_metadata", return_value=None)
    def test_skips_entry_when_retrieve_returns_none(
        self, m_retrieve, m_write_files, cloud
    ):
        """Skip entries where retrieve_metadata returns None."""
        files = [
            {
                "path": "/var/lib/cloud/instance/metadata",
                "data": [{"metadata": "missing-key"}],
            }
        ]
        cc_write_metadata.write_metadata("cc_write_metadata", files, cloud)
        assert 1 == m_retrieve.call_count
        assert 1 == m_write_files.call_count

    @pytest.mark.parametrize(
        "files,content,expected_path",
        [
            (
                [
                    {
                        "path": "/var/lib/cloud/instance/.instance-id",
                        "data": [{"metadata": "instance-id"}],
                    }
                ],
                "i-1234567890abcdef0",
                "/var/lib/cloud/instance/.instance-id",
            ),
            (
                [
                    {
                        "path": "/etc/cloud/instance-region",
                        "data": [{"metadata": "region"}],
                    }
                ],
                "us-east-1",
                "/etc/cloud/instance-region",
            ),
        ],
    )
    @mock.patch(M_PATH + "cc_write_files.write_files")
    @mock.patch(M_PATH + "retrieve_metadata")
    def test_write_files_parameters(
        self, m_retrieve, m_write_files, cloud, files, content, expected_path
    ):
        """Test write_files is called with correct parameters and file info."""
        m_retrieve.return_value = content
        cc_write_metadata.write_metadata("cc_write_metadata", files, cloud)
        
        # Verify write_files was called
        assert m_write_files.called
        
        # Verify module name and owner
        assert "cc_write_metadata" == m_write_files.call_args[0][0]
        assert cloud.distro.default_owner == m_write_files.call_args[0][2]
        
        # Verify file info
        call_args = m_write_files.call_args
        files_arg = call_args[0][1]
        assert files_arg[0]["permissions"] == cc_write_metadata.cc_write_files.DEFAULT_PERMS
        assert files_arg[0]["content"] == content
        assert files_arg[0]["path"] == expected_path

    @pytest.mark.parametrize(
        "files,keys_to_check_removed",
        [
            (
                [
                    {
                        "path": "/var/lib/cloud/instance/.instance-id",
                        "data": [{"metadata": "instance-id"}],
                        "metadata": "should_be_removed",
                        "identity": "should_be_removed",
                    }
                ],
                ["metadata", "identity"],
            ),
        ],
    )
    @mock.patch(M_PATH + "cc_write_files.write_files")
    @mock.patch(M_PATH + "retrieve_metadata", return_value="i-1234567890abcdef0")
    def test_removes_keys_from_file_info(
        self, m_retrieve, m_write_files, cloud, files, keys_to_check_removed
    ):
        """Test that specific keys are removed from file info."""
        cc_write_metadata.write_metadata("cc_write_metadata", files, cloud)
        
        call_args = m_write_files.call_args
        files_arg = call_args[0][1]
        for key in keys_to_check_removed:
            assert key not in files_arg[0]


class TestWriteMetadataSchema:
    """Tests for write_metadata schema validation."""

    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {
                    "write_metadata": [
                        {
                            "path": "/root/.instance-id",
                            "data": [{"metadata": "instance-id"}, "unknown"],
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "write_metadata": [
                        {
                            "path": "/root/.instance-id",
                            "data": [{"metadata": "instance-id"}, "unknown"],
                        },
                        {
                            "path": "/root/.region",
                            "data": [{"identity": "region"}, "unknown"],
                        },
                    ]
                },
                None,
            ),
            (
                {"write_metadata": [{"data": [{"metadata": "instance-id"}]}]},
                "'path' is a required property",
            ),
            (
                {"write_metadata": [{"path": "/tmp/test"}]},
                "'data' is a required property",
            ),
            (
                {"write_metadata": "not_an_array"},
                "write_metadata: 'not_an_array' is not of type 'array'",
            ),
            (
                {"write_metadata": []},
                None,
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Validate write_metadata schema."""
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestWriteMetadataIntegration:
    """Integration tests for write_metadata module."""

    @pytest.mark.parametrize(
        "file_path,data_config,expected_content",
        [
            (
                "/var/lib/cloud/instance/.instance-id",
                [{"metadata": "instance-id"}, "no-instance-id"],
                "i-1234567890abcdef0",
            ),
            (
                "/etc/cloud/instance-region",
                [{"identity": "region"}, "unknown-region"],
                "us-east-1",
            ),
            (
                "/var/lib/cloud/instance/.account-id",
                [{"identity": "account-id"}, "no-account-id"],
                "123456789012",
            ),
            (
                "/var/lib/cloud/instance/.availability-zone",
                [{"metadata": "availability-zone"}, "unknown-az"],
                "us-east-1a",
            ),
        ],
    )
    @pytest.mark.usefixtures("fake_filesystem")
    @mock.patch("cloudinit.config.cc_write_files.write_files")
    def test_writes_metadata_to_file(
        self, m_write_files, cloud, file_path, data_config, expected_content
    ):
        """Test writing various metadata types to files."""
        cfg = {
            "write_metadata": [
                {
                    "path": file_path,
                    "data": data_config,
                }
            ]
        }
        cc_write_metadata.handle("cc_write_metadata", cfg, cloud, [])
        
        assert m_write_files.called
        files_arg = m_write_files.call_args[0][1]
        assert len(files_arg) == 1
        assert files_arg[0]["path"] == file_path
        assert files_arg[0]["content"] == expected_content
