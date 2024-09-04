# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.
import re

import pytest

from cloudinit import helpers, settings, util
from cloudinit.sources import DataSourceAeza as aeza
from cloudinit.sources import InvalidMetaDataException
from tests.unittests.helpers import mock

METADATA = util.load_yaml(
    """---
hostname: cloudinit-test.aeza.network
instance-id: ic0859a7003d840d093756680cb45d51f
public-keys:
- ssh-ed25519 AAAA...4nkhmWh example-key
"""
)

VENDORDATA = None

USERDATA = b"""#cloud-config
runcmd:
- [touch, /root/cloud-init-worked]
"""


M_PATH = "cloudinit.sources.DataSourceAeza."


class TestDataSourceAeza:
    """Test Aeza.net reading instance-data"""

    @pytest.mark.parametrize(
        "system_manufacturer,expected",
        (
            pytest.param("Aeza", True, id="dmi_platform_match_aeza"),
            pytest.param("aeza", False, id="dmi_platform_match_case_sensitve"),
            pytest.param("Aezanope", False, id="dmi_platform_strict_match"),
        ),
    )
    @mock.patch(f"{M_PATH}dmi.read_dmi_data")
    def test_ds_detect(self, m_read_dmi_data, system_manufacturer, expected):
        """Only strict case-senstiive match on DMI system-manfacturer Aeza"""
        m_read_dmi_data.return_value = system_manufacturer
        assert expected is aeza.DataSourceAeza.ds_detect()

    @pytest.mark.parametrize(
        "sys_cfg,expected_calls",
        (
            pytest.param(
                {},
                [
                    mock.call(
                        "http://77.221.156.49/v1/cloudinit/1dd9a779-uuid/%s",
                        timeout=10,
                        retries=5,
                    )
                ],
                id="default_sysconfig_ds_url_retry_and_timeout",
            ),
            pytest.param(
                {
                    "datasource": {
                        "Aeza": {
                            "timeout": 7,
                            "retries": 8,
                            "metadata_url": "https://somethingelse/",
                        }
                    }
                },
                [
                    mock.call(
                        "https://somethingelse/%s",
                        timeout=7,
                        retries=8,
                    )
                ],
                id="custom_sysconfig_ds_url_retry_and_timeout_overrides",
            ),
        ),
    )
    @mock.patch("cloudinit.util.read_seeded")
    @mock.patch(f"{M_PATH}dmi.read_dmi_data")
    def test_read_data(
        self,
        m_read_dmi_data,
        m_read_seeded,
        sys_cfg,
        expected_calls,
        paths,
        tmpdir,
    ):
        m_read_dmi_data.return_value = "1dd9a779-uuid"
        m_read_seeded.return_value = (METADATA, USERDATA, VENDORDATA)

        ds = aeza.DataSourceAeza(
            sys_cfg=sys_cfg, distro=mock.Mock(), paths=paths
        )
        with mock.patch.object(ds, "ds_detect", return_value=True):
            assert True is ds.get_data()

        assert m_read_seeded.call_args_list == expected_calls
        assert ds.get_public_ssh_keys() == METADATA.get("public-keys")
        assert isinstance(ds.get_public_ssh_keys(), list)
        assert ds.userdata_raw == USERDATA
        assert ds.vendordata_raw == VENDORDATA

    @pytest.mark.parametrize(
        "metadata,userdata,error_msg",
        (
            ({}, USERDATA, "Metadata does not contain instance-id: {}"),
            (
                None,
                USERDATA,
                "Failed to read metadata from http://77.221.156.49/v1/cloudinit/1dd9a779-uuid/%s",
            ),
            ({"instance-id": "yep"}, "non-bytes", "Userdata is not bytes"),
        ),
    )
    @mock.patch("cloudinit.util.read_seeded")
    @mock.patch(f"{M_PATH}dmi.read_dmi_data")
    def test_not_detected_on_invalid_instance_data(
        self,
        m_read_dmi_data,
        m_read_seeded,
        metadata,
        userdata,
        error_msg,
        paths,
    ):
        """Assert get_data returns False for unexpected format conditions."""
        m_read_dmi_data.return_value = "1dd9a779-uuid"
        m_read_seeded.return_value = (metadata, userdata, VENDORDATA)

        ds = aeza.DataSourceAeza(sys_cfg={}, distro=mock.Mock(), paths=paths)
        with pytest.raises(
            InvalidMetaDataException, match=re.escape(error_msg)
        ):
            with mock.patch.object(ds, "ds_detect", return_value=True):
                ds.get_data()
