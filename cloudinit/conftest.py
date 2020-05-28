from unittest import mock

import pytest

from cloudinit import util


@pytest.yield_fixture(autouse=True)
def disable_subp_usage(request):
    """
    Across all (pytest) tests, ensure that util.subp is not invoked.

    Note that this can only catch invocations where the util module is imported
    and ``util.subp(...)`` is called.  ``from cloudinit.util import subp``
    imports happen before the patching here (or the CiTestCase monkey-patching)
    happens, so are left untouched.

    To allow a particular test method or class to use util.subp you can set the
    parameter passed to this fixture to False using pytest.mark.parametrize::

        @pytest.mark.parametrize("disable_subp_usage", [False], indirect=True)
        def test_whoami(self):
            util.subp(["whoami"])

    To instead allow util.subp usage for a specific command, you can set the
    parameter passed to this fixture to that command:

        @pytest.mark.parametrize("disable_subp_usage", ["bash"], indirect=True)
        def test_bash(self):
            util.subp(["bash"])

    To specify multiple commands, set the parameter to a list (note the
    double-layered list: we specify a single parameter that is itself a list):

        @pytest.mark.parametrize(
            "disable_subp_usage", ["bash", "whoami"], indirect=True)
        def test_several_things(self):
            util.subp(["bash"])
            util.subp(["whoami"])

    This fixture (roughly) mirrors the functionality of
    CiTestCase.allowed_subp.  N.B. While autouse fixtures do affect non-pytest
    tests, CiTestCase's allowed_subp does take precedence (and we have
    TestDisableSubpUsageInTestSubclass to confirm that).
    """
    should_disable = getattr(request, "param", True)
    if should_disable:
        if not isinstance(should_disable, (list, str)):
            def side_effect(args, *other_args, **kwargs):
                raise AssertionError("Unexpectedly used util.subp")
        else:
            # Look this up before our patch is in place, so we have access to
            # the real implementation in side_effect
            subp = util.subp

            if isinstance(should_disable, str):
                should_disable = [should_disable]

            def side_effect(args, *other_args, **kwargs):
                cmd = args[0]
                if cmd not in should_disable:
                    raise AssertionError(
                        "Unexpectedly used util.subp to call {} (allowed:"
                        " {})".format(cmd, ",".join(should_disable))
                    )
                return subp(args, *other_args, **kwargs)

        with mock.patch('cloudinit.util.subp', autospec=True) as m_subp:
            m_subp.side_effect = side_effect
            yield
    else:
        yield
