from unittest import mock

import pytest


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

    This fixture (roughly) mirrors the functionality of
    CiTestCase.allowed_subp.

    TODO:
        * Enable select subp usage (i.e. allowed_subp=[...])
    """
    should_disable = getattr(request, "param", True)
    if should_disable:
        with mock.patch('cloudinit.util.subp', autospec=True) as m_subp:
            m_subp.side_effect = AssertionError("Unexpectedly used util.subp")
            yield
    else:
        yield
