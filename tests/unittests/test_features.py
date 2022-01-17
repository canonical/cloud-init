# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=no-member,no-name-in-module
"""
This file is for testing the feature flag functionality itself,
NOT for testing any individual feature flag
"""
import sys
from pathlib import Path

import pytest

import cloudinit


@pytest.fixture()
def create_override(request):
    """
    Create a feature overrides file and do some module wizardry to make
    it seem like we're importing the features file for the first time.

    After creating the override file with the values passed by the test,
    we need to reload cloudinit.features
    to get all of the current features (including the overridden ones).
    Once the test is complete, we remove the file we created and set
    features and feature_overrides modules to how they were before
    the test started
    """
    override_path = Path(cloudinit.__file__).parent / "feature_overrides.py"
    if override_path.exists():
        raise Exception(
            "feature_overrides.py unexpectedly exists! "
            "Remove it to run this test."
        )
    with override_path.open("w") as f:
        for key, value in request.param.items():
            f.write("{} = {}\n".format(key, value))

    sys.modules.pop("cloudinit.features", None)

    yield

    override_path.unlink()
    sys.modules.pop("cloudinit.feature_overrides", None)


class TestFeatures:
    def test_feature_without_override(self):
        from cloudinit.features import ERROR_ON_USER_DATA_FAILURE

        assert ERROR_ON_USER_DATA_FAILURE is True

    @pytest.mark.parametrize(
        "create_override",
        [{"ERROR_ON_USER_DATA_FAILURE": False}],
        indirect=True,
    )
    def test_feature_with_override(self, create_override):
        from cloudinit.features import ERROR_ON_USER_DATA_FAILURE

        assert ERROR_ON_USER_DATA_FAILURE is False

    @pytest.mark.parametrize(
        "create_override", [{"SPAM": True}], indirect=True
    )
    def test_feature_only_in_override(self, create_override):
        from cloudinit.features import SPAM

        assert SPAM is True
