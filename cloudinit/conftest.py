from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def disable_subp_usage():
    """
    Across all (pytest) tests, ensure that util.subp is not invoked.

    Note that this can only catch invocations where the util module is imported
    and ``util.subp(...)`` is called.  ``from cloudinit.util import subp``
    imports happen before the patching here (or the CiTestCase monkey-patching)
    happens, so are left untouched.

    This mirrors the functionality of CiTestCase.allowed_subp.

    TODO:
        * Re-enable subp usage (i.e. allowed_subp=True)
        * Enable select subp usage (i.e. allowed_subp=[...])
    """

    with mock.patch('cloudinit.util.subp', autospec=True) as m_subp:
        m_subp.side_effect = AssertionError("Unexpectedly used util.subp")
        yield
