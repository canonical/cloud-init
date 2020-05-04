import pytest

from cloudinit import util
from cloudinit.tests.helpers import CiTestCase


class TestDisableSubpUsage:
    """Test that the disable_subp_usage fixture behaves as expected."""

    def test_using_subp_raises_assertion_error(self):
        with pytest.raises(AssertionError):
            util.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            util.subp()

    @pytest.mark.parametrize('disable_subp_usage', [False], indirect=True)
    def test_subp_usage_can_be_reenabled(self):
        util.subp(['whoami'])


class TestDisableSubpUsageInTestSubclass(CiTestCase):
    """Test that disable_subp_usage doesn't impact CiTestCase's subp logic."""

    def test_using_subp_raises_assertion_error(self):
        with pytest.raises(Exception):
            util.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            util.subp()

    def test_subp_usage_can_be_reenabled(self):
        _old_allowed_subp = self.allow_subp
        self.allowed_subp = True
        try:
            util.subp(['whoami'])
        finally:
            self.allowed_subp = _old_allowed_subp
