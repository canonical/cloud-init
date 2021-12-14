# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Tests for cloudinit/distros/__init__.py"""

from unittest import mock

import pytest

from cloudinit.distros import LDH_ASCII_CHARS, _get_package_mirror_info

# In newer versions of Python, these characters will be omitted instead
# of substituted because of security concerns.
# See https://bugs.python.org/issue43882
SECURITY_URL_CHARS = "\n\r\t"

# Define a set of characters we would expect to be replaced
INVALID_URL_CHARS = [
    chr(x)
    for x in range(127)
    if chr(x) not in LDH_ASCII_CHARS + SECURITY_URL_CHARS
]
for separator in [":", ".", "/", "#", "?", "@", "[", "]"]:
    # Remove from the set characters that either separate hostname parts (":",
    # "."), terminate hostnames ("/", "#", "?", "@"), or cause Python to be
    # unable to parse URLs ("[", "]").
    INVALID_URL_CHARS.remove(separator)


class TestGetPackageMirrorInfo:
    """
    Tests for cloudinit.distros._get_package_mirror_info.

    These supplement the tests in tests/unittests/test_distros/test_generic.py
    which are more focused on testing a single production-like configuration.
    These tests are more focused on specific aspects of the unit under test.
    """

    @pytest.mark.parametrize(
        "mirror_info,expected",
        [
            # Empty info gives empty return
            ({}, {}),
            # failsafe values used if present
            (
                {
                    "failsafe": {
                        "primary": "http://value",
                        "security": "http://other",
                    }
                },
                {"primary": "http://value", "security": "http://other"},
            ),
            # search values used if present
            (
                {
                    "search": {
                        "primary": ["http://value"],
                        "security": ["http://other"],
                    }
                },
                {"primary": ["http://value"], "security": ["http://other"]},
            ),
            # failsafe values used if search value not present
            (
                {
                    "search": {"primary": ["http://value"]},
                    "failsafe": {"security": "http://other"},
                },
                {"primary": ["http://value"], "security": "http://other"},
            ),
        ],
    )
    def test_get_package_mirror_info_failsafe(self, mirror_info, expected):
        """
        Test the interaction between search and failsafe inputs

        (This doesn't test the case where the mirror_filter removes all search
        options; test_failsafe_used_if_all_search_results_filtered_out covers
        that.)
        """
        assert expected == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: x
        )

    def test_failsafe_used_if_all_search_results_filtered_out(self):
        """Test the failsafe option used if all search options eliminated."""
        mirror_info = {
            "search": {"primary": ["http://value"]},
            "failsafe": {"primary": "http://other"},
        }
        assert {"primary": "http://other"} == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: False
        )

    @pytest.mark.parametrize(
        "allow_ec2_mirror, platform_type", [(True, "ec2")]
    )
    @pytest.mark.parametrize(
        "availability_zone,region,patterns,expected",
        (
            # Test ec2_region alone
            (
                "fk-fake-1f",
                None,
                ["http://EC2-%(ec2_region)s/ubuntu"],
                ["http://ec2-fk-fake-1/ubuntu"],
            ),
            # Test availability_zone alone
            (
                "fk-fake-1f",
                None,
                ["http://AZ-%(availability_zone)s/ubuntu"],
                ["http://az-fk-fake-1f/ubuntu"],
            ),
            # Test region alone
            (
                None,
                "fk-fake-1",
                ["http://RG-%(region)s/ubuntu"],
                ["http://rg-fk-fake-1/ubuntu"],
            ),
            # Test that ec2_region is not available for non-matching AZs
            (
                "fake-fake-1f",
                None,
                [
                    "http://EC2-%(ec2_region)s/ubuntu",
                    "http://AZ-%(availability_zone)s/ubuntu",
                ],
                ["http://az-fake-fake-1f/ubuntu"],
            ),
            # Test that template order maintained
            (
                None,
                "fake-region",
                [
                    "http://RG-%(region)s-2/ubuntu",
                    "http://RG-%(region)s-1/ubuntu",
                ],
                [
                    "http://rg-fake-region-2/ubuntu",
                    "http://rg-fake-region-1/ubuntu",
                ],
            ),
            # Test that non-ASCII hostnames are IDNA encoded;
            # "IDNA-ТεЅТ̣".encode('idna') == b"xn--idna--4kd53hh6aba3q"
            (
                None,
                "ТεЅТ̣",
                ["http://www.IDNA-%(region)s.com/ubuntu"],
                ["http://www.xn--idna--4kd53hh6aba3q.com/ubuntu"],
            ),
            # Test that non-ASCII hostnames with a port are IDNA encoded;
            # "IDNA-ТεЅТ̣".encode('idna') == b"xn--idna--4kd53hh6aba3q"
            (
                None,
                "ТεЅТ̣",
                ["http://www.IDNA-%(region)s.com:8080/ubuntu"],
                ["http://www.xn--idna--4kd53hh6aba3q.com:8080/ubuntu"],
            ),
            # Test that non-ASCII non-hostname parts of URLs are unchanged
            (
                None,
                "ТεЅТ̣",
                ["http://www.example.com/%(region)s/ubuntu"],
                ["http://www.example.com/ТεЅТ̣/ubuntu"],
            ),
            # Test that IPv4 addresses are unchanged
            (
                None,
                "fk-fake-1",
                ["http://192.168.1.1:8080/%(region)s/ubuntu"],
                ["http://192.168.1.1:8080/fk-fake-1/ubuntu"],
            ),
            # Test that IPv6 addresses are unchanged
            (
                None,
                "fk-fake-1",
                ["http://[2001:67c:1360:8001::23]/%(region)s/ubuntu"],
                ["http://[2001:67c:1360:8001::23]/fk-fake-1/ubuntu"],
            ),
            # Test that unparseable URLs are filtered out of the mirror list
            (
                None,
                "inv[lid",
                [
                    "http://%(region)s.in.hostname/should/be/filtered",
                    "http://but.not.in.the.path/%(region)s",
                ],
                ["http://but.not.in.the.path/inv[lid"],
            ),
            (
                None,
                "-some-region-",
                ["http://-lead-ing.%(region)s.trail-ing-.example.com/ubuntu"],
                ["http://lead-ing.some-region.trail-ing.example.com/ubuntu"],
            ),
        )
        + tuple(
            # Dynamically generate a test case for each non-LDH
            # (Letters/Digits/Hyphen) ASCII character, testing that it is
            # substituted with a hyphen
            (
                None,
                "fk{0}fake{0}1".format(invalid_char),
                ["http://%(region)s/ubuntu"],
                ["http://fk-fake-1/ubuntu"],
            )
            for invalid_char in INVALID_URL_CHARS
        ),
    )
    def test_valid_substitution(
        self,
        allow_ec2_mirror,
        platform_type,
        availability_zone,
        region,
        patterns,
        expected,
    ):
        """Test substitution works as expected."""
        flag_path = (
            "cloudinit.distros.ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES"
        )

        m_data_source = mock.Mock(
            availability_zone=availability_zone,
            region=region,
            platform_type=platform_type,
        )
        mirror_info = {"search": {"primary": patterns}}

        with mock.patch(flag_path, allow_ec2_mirror):
            ret = _get_package_mirror_info(
                mirror_info,
                data_source=m_data_source,
                mirror_filter=lambda x: x,
            )
        print(allow_ec2_mirror)
        print(platform_type)
        print(availability_zone)
        print(region)
        print(patterns)
        print(expected)
        assert {"primary": expected} == ret
