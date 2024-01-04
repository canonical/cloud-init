import pytest

from cloudinit import subp
from conftest import UnexpectedSubpError
from tests.unittests.helpers import CiTestCase


class TestDisableSubpUsage:
    """Test that the disable_subp_usage fixture behaves as expected."""

    def test_using_subp_raises_assertion_error(self):
        with pytest.raises(UnexpectedSubpError):
            subp.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            # We are intentionally passing no value for a parameter, so:
            #  pylint: disable=no-value-for-parameter
            subp.subp()

    def test_subp_exception_escapes_exception_handling(self):
        with pytest.raises(UnexpectedSubpError):
            try:
                subp.subp(["some", "args"])
            except Exception:
                pytest.fail("Unexpected exception raised")

    @pytest.mark.allow_all_subp
    def test_subp_usage_can_be_reenabled(self):
        subp.subp(["whoami"])

    @pytest.mark.allow_subp_for("whoami")
    def test_subp_usage_can_be_conditionally_reenabled(self):
        # The two parameters test each potential invocation with a single
        # argument
        with pytest.raises(UnexpectedSubpError) as excinfo:
            subp.subp(["some", "args"])
        assert "allowed: whoami" in str(excinfo.value)
        subp.subp(["whoami"])

    @pytest.mark.allow_subp_for("whoami", "bash")
    def test_subp_usage_can_be_conditionally_reenabled_for_multiple_cmds(self):
        with pytest.raises(UnexpectedSubpError) as excinfo:
            subp.subp(["some", "args"])
        assert "allowed: whoami,bash" in str(excinfo.value)
        subp.subp(["bash", "-c", "true"])
        subp.subp(["whoami"])

    @pytest.mark.allow_all_subp
    @pytest.mark.allow_subp_for("bash")
    def test_both_marks_raise_an_error(self):
        with pytest.raises(UnexpectedSubpError, match="marked both"):
            subp.subp(["bash"])


class TestDisableSubpUsageInTestSubclass(CiTestCase):
    """Test that disable_subp_usage doesn't impact CiTestCase's subp logic."""

    def test_using_subp_raises_exception(self):
        with pytest.raises(Exception):
            subp.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            subp.subp()

    def test_subp_usage_can_be_reenabled(self):
        _old_allowed_subp = self.allow_subp
        self.allowed_subp = True
        try:
            subp.subp(["bash", "-c", "true"])
        finally:
            self.allowed_subp = _old_allowed_subp
