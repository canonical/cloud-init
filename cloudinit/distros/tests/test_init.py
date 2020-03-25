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
        ({'failsafe': {'primary': 'http://value', 'security': 'http://other'}},
         {'primary': 'http://value', 'security': 'http://other'}),
        # search values used if present
        ({'search': {'primary': ['http://value'],
                     'security': ['http://other']}},
         {'primary': ['http://value'], 'security': ['http://other']}),
        # failsafe values used if search value not present
        ({'search': {'primary': ['http://value']},
          'failsafe': {'security': 'http://other'}},
         {'primary': ['http://value'], 'security': 'http://other'})
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
            'search': {'primary': ['http://value']},
            'failsafe': {'primary': 'http://other'}
        }
        assert {'primary': 'http://other'} == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: False)

    @pytest.mark.parametrize('availability_zone,region,patterns,expected', (
        # Test ec2_region alone
        ('fk-fake-1f', None, ['http://EC2-%(ec2_region)s/ubuntu'],
         ['http://ec2-fk-fake-1/ubuntu']),
        # Test availability_zone alone
        ('fk-fake-1f', None, ['http://AZ-%(availability_zone)s/ubuntu'],
         ['http://az-fk-fake-1f/ubuntu']),
        # Test region alone
        (None, 'fk-fake-1', ['http://RG-%(region)s/ubuntu'],
         ['http://rg-fk-fake-1/ubuntu']),
        # Test that ec2_region is not available for non-matching AZs
        ('fake-fake-1f', None,
         ['http://EC2-%(ec2_region)s/ubuntu',
          'http://AZ-%(availability_zone)s/ubuntu'],
         ['http://az-fake-fake-1f/ubuntu']),
        # Test that template order maintained
        (None, 'fake-region',
         ['http://RG-%(region)s-2/ubuntu', 'http://RG-%(region)s-1/ubuntu'],
         ['http://rg-fake-region-2/ubuntu', 'http://rg-fake-region-1/ubuntu']),
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
