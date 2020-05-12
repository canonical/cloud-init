import pytest

from cloudinit import util


class TestDisableSubpUsage:

    def test_using_subp_raises_assertion_error(self):
        with pytest.raises(AssertionError):
            util.subp(["some", "args"])

    def test_typeerrors_on_incorrect_usage(self):
        with pytest.raises(TypeError):
            util.subp()

    @pytest.mark.parametrize('disable_subp_usage', [False], indirect=True)
    def test_subp_usage_can_be_reenabled(self):
        util.subp(['whoami'])
