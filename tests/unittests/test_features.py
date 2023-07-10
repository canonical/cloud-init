# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=no-member,no-name-in-module
"""
This file is for testing the feature flag functionality itself,
NOT for testing any individual feature flag
"""
from unittest import mock

from cloudinit import features


class TestGetFeatures:
    """default pytest-xdist behavior may fail due to these tests"""

    def test_feature_without_override(self):
        assert {
            "ERROR_ON_USER_DATA_FAILURE": True,
            "EXPIRE_APPLIES_TO_HASHED_USERS": True,
            "NETPLAN_CONFIG_ROOT_READ_ONLY": True,
            "NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH": True,
        } == features.get_features()
        with mock.patch.object(
            features, "NETPLAN_CONFIG_ROOT_READ_ONLY", False
        ):
            assert {
                "ERROR_ON_USER_DATA_FAILURE": True,
                "EXPIRE_APPLIES_TO_HASHED_USERS": True,
                "NETPLAN_CONFIG_ROOT_READ_ONLY": False,
                "NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH": True,
            } == features.get_features()
