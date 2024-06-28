# This file is part of cloud-init. See LICENSE file for license information.
"""
This file is for testing the feature flag functionality itself,
NOT for testing any individual feature flag
"""
from unittest import mock

from cloudinit import features


class TestGetFeatures:
    def test_feature_without_override(self):
        # Since features are intended to be overridden downstream, mock them
        # all here so new feature flags don't require a new change to this
        # unit test.
        with mock.patch.multiple(
            "cloudinit.features",
            ERROR_ON_USER_DATA_FAILURE=True,
            ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES=True,
            EXPIRE_APPLIES_TO_HASHED_USERS=False,
            NETPLAN_CONFIG_ROOT_READ_ONLY=True,
            DEPRECATION_INFO_BOUNDARY="devel",
            NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH=False,
            APT_DEB822_SOURCE_LIST_FILE=True,
        ):
            assert {
                "ERROR_ON_USER_DATA_FAILURE": True,
                "ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES": True,
                "EXPIRE_APPLIES_TO_HASHED_USERS": False,
                "NETPLAN_CONFIG_ROOT_READ_ONLY": True,
                "NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH": False,
                "APT_DEB822_SOURCE_LIST_FILE": True,
                "DEPRECATION_INFO_BOUNDARY": "devel",
            } == features.get_features()
