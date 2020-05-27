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
            # We are intentionally passing no value for a parameter, so:
            #  pylint: disable=no-value-for-parameter
            util.subp()

    @pytest.mark.parametrize('disable_subp_usage', [False], indirect=True)
    def test_subp_usage_can_be_reenabled(self):
        util.subp(['whoami'])

    @pytest.mark.parametrize(
        'disable_subp_usage', [['whoami'], 'whoami'], indirect=True)
    def test_subp_usage_can_be_conditionally_reenabled(self):
        # The two parameters test each potential invocation with a single
        # argument
        with pytest.raises(AssertionError) as excinfo:
            util.subp(["some", "args"])
        assert "allowed: whoami" in str(excinfo.value)
        util.subp(['whoami'])

    @pytest.mark.parametrize(
        'disable_subp_usage', [['whoami', 'bash']], indirect=True)
    def test_subp_usage_can_be_conditionally_reenabled_for_multiple_cmds(self):
        with pytest.raises(AssertionError) as excinfo:
            util.subp(["some", "args"])
        assert "allowed: whoami,bash" in str(excinfo.value)
        util.subp(['bash', '-c', 'true'])
        util.subp(['whoami'])


class TestDisableSubpUsageInTestSubclass(CiTestCase):
    """Test that disable_subp_usage doesn't impact CiTestCase's subp logic."""

    def test_using_subp_raises_exception(self):
        with pytest.raises(Exception):
            util.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            util.subp()

    def test_subp_usage_can_be_reenabled(self):
        _old_allowed_subp = self.allow_subp
        self.allowed_subp = True
        try:
            util.subp(['bash', '-c', 'true'])
        finally:
            self.allowed_subp = _old_allowed_subp
