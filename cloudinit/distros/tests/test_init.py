# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Tests for cloudinit/distros/__init__.py"""

from unittest import mock

import pytest

from cloudinit.distros import _get_package_mirror_info


class TestGetPackageMirrorInfo:
    """
    Tests for cloudinit.distros._get_package_mirror_info.

    These supplement the tests in tests/unittests/test_distros/test_generic.py
    which are more focused on testing a single production-like configuration.
    These tests are more focused on specific aspects of the unit under test.
    """

    @pytest.mark.parametrize('mirror_info,expected', [
        # Empty info gives empty return
        ({}, {}),
        # failsafe values used if present
        ({'failsafe': {'primary': 'value', 'security': 'other'}},
         {'primary': 'value', 'security': 'other'}),
        # search values used if present
        ({'search': {'primary': ['value'], 'security': ['other']}},
         {'primary': ['value'], 'security': ['other']}),
        # failsafe values used if search value not present
        ({'search': {'primary': ['value']}, 'failsafe': {'security': 'other'}},
         {'primary': ['value'], 'security': 'other'})
    ])
    def test_get_package_mirror_info_failsafe(self, mirror_info, expected):
        """
        Test the interaction between search and failsafe inputs

        (This doesn't test the case where the mirror_filter removes all search
        options; test_failsafe_used_if_all_search_results_filtered_out covers
        that.)
        """
        assert expected == _get_package_mirror_info(mirror_info,
                                                    mirror_filter=lambda x: x)

    def test_failsafe_used_if_all_search_results_filtered_out(self):
        """Test the failsafe option used if all search options eliminated."""
        mirror_info = {
            'search': {'primary': ['value']}, 'failsafe': {'primary': 'other'}
        }
        assert {'primary': 'other'} == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: False)

    @pytest.mark.parametrize('availability_zone,region,patterns,expected', (
        # Test ec2_region alone
        ('fk-fake-1f', None, ['EC2-%(ec2_region)s'], ['EC2-fk-fake-1']),
        # Test availability_zone alone
        ('fk-fake-1f', None, ['AZ-%(availability_zone)s'], ['AZ-fk-fake-1f']),
        # Test region alone
        (None, 'fk-fake-1', ['RG-%(region)s'], ['RG-fk-fake-1']),
        # Test that ec2_region is not available for non-matching AZs
        ('fake-fake-1f', None,
         ['EC2-%(ec2_region)s', 'AZ-%(availability_zone)s'],
         ['AZ-fake-fake-1f']),
        # Test that template order maintained
        (None, 'fake-region', ['RG-%(region)s-2', 'RG-%(region)s-1'],
         ['RG-fake-region-2', 'RG-fake-region-1']),
    ))
    def test_substitution(self, availability_zone, region, patterns, expected):
        """Test substitution works as expected."""
        m_data_source = mock.Mock(
            availability_zone=availability_zone, region=region
        )
        mirror_info = {'search': {'primary': patterns}}

        ret = _get_package_mirror_info(
            mirror_info,
            data_source=m_data_source,
            mirror_filter=lambda x: x
        )
        assert {'primary': expected} == ret
