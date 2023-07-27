from typing import Any, Dict

import pytest

from cloudinit.sources.helpers.akamai import get_dmi_config, is_on_akamai
from tests.unittests.helpers import mock


class TestAkamaiHelper:
    """
    Test for the Akamai helper functions
    """

    @pytest.mark.parametrize(
        "dmi_config,expected_result",
        (
            # no content
            ("", {}),
            # stage control flags
            (
                "als=0;ais=0",
                {"allow_local_stage": False, "allow_init_stage": False},
            ),
            # networking flags
            (
                "v4=0;v6=0;dhcp=0",
                {
                    "allow_ipv4": False,
                    "allow_ipv6": False,
                    "allow_dhcp": False,
                },
            ),
            # interface prefix overrides
            ("pmp=ab:cd:", {"preferred_mac_prefixes": ["ab:cd:"]}),
            (
                "pmp=ab:cd:,12:34:",
                {"preferred_mac_prefixes": ["ab:cd:", "12:34:"]},
            ),
            # unrecognized data
            ("unrecognized", {}),
            (",;", {}),
        ),
    )
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_get_dmi_config(
        self, read_dmi_data, dmi_config: str, expected_result: Dict[str, Any]
    ):
        """
        Tests that dmi-based configuration overrides parse as expected
        """
        read_dmi_data.return_value = dmi_config
        result = get_dmi_config()

        assert (
            result == expected_result
        ), f"Unexpected result parsing dmi config '{dmi_config}'!"
        assert [
            mock.call("baseboard-serial-number")
        ] == read_dmi_data.call_args_list

    @pytest.mark.parametrize(
        "dmi_data,expected_result",
        (
            ("Akamai", True),
            ("Linode", True),
            ("GCE", False),
            ("EC2", False),
            ("", False),
        ),
    )
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_is_on_akamai(
        self, read_dmi_data, dmi_data: str, expected_result: bool
    ):
        """
        Tests that is_on_akamai correctly detects if we are on Akama's platform
        """
        read_dmi_data.return_value = dmi_data
        result = is_on_akamai()

        assert (
            result == expected_result
        ), f"Unexpected result checking if '{dmi_data}' is Akamai"
        assert [
            mock.call("system-manufacturer")
        ] == read_dmi_data.call_args_list
