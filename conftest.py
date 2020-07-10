from unittest import mock

import pytest

from cloudinit import subp


def _closest_marker_args_or(request, marker_name: str, default):
    """Get the args for the closest ``marker_name`` or return ``default``"""
    try:
        marker = request.node.get_closest_marker(marker_name)
    except AttributeError:
        # Older versions of pytest don't have the new API
        marker = request.node.get_marker(marker_name)
    if marker is not None:
        return marker.args
    return default


@pytest.yield_fixture(autouse=True)
def disable_subp_usage(request):
    """
    Across all (pytest) tests, ensure that subp.subp is not invoked.

    Note that this can only catch invocations where the util module is imported
    and ``subp.subp(...)`` is called.  ``from cloudinit.subp mport subp``
    imports happen before the patching here (or the CiTestCase monkey-patching)
    happens, so are left untouched.

    To allow a particular test method or class to use subp.subp you can mark it
    as such::

        @pytest.mark.allow_all_subp
        def test_whoami(self):
            subp.subp(["whoami"])

    To instead allow subp.subp usage for a specific command, you can use the
    ``allow_subp_for`` mark::

        @pytest.mark.allow_subp_for("bash")
        def test_bash(self):
            subp.subp(["bash"])

    You can pass multiple commands as values; they will all be permitted::

        @pytest.mark.allow_subp_for("bash", "whoami")
        def test_several_things(self):
            subp.subp(["bash"])
            subp.subp(["whoami"])

    This fixture (roughly) mirrors the functionality of
    CiTestCase.allowed_subp.  N.B. While autouse fixtures do affect non-pytest
    tests, CiTestCase's allowed_subp does take precedence (and we have
    TestDisableSubpUsageInTestSubclass to confirm that).
    """
    allow_subp_for = _closest_marker_args_or(request, "allow_subp_for", None)
    # Because the mark doesn't take arguments, `allow_all_subp` will be set to
    # [] if the marker is present, so explicit None checks are required
    allow_all_subp = _closest_marker_args_or(request, "allow_all_subp", None)

    if allow_all_subp is not None and allow_subp_for is None:
        # Only allow_all_subp specified, don't mock subp.subp
        yield
        return

    if allow_all_subp is None and allow_subp_for is None:
        # No marks, default behaviour; disallow all subp.subp usage
        def side_effect(args, *other_args, **kwargs):
            raise AssertionError("Unexpectedly used subp.subp")

    elif allow_all_subp is not None and allow_subp_for is not None:
        # Both marks, ambiguous request; raise an exception on all subp usage
        def side_effect(args, *other_args, **kwargs):
            raise AssertionError(
                "Test marked both allow_all_subp and allow_subp_for: resolve"
                " this either by modifying your test code, or by modifying"
                " disable_subp_usage to handle precedence."
            )
    else:
        # Look this up before our patch is in place, so we have access to
        # the real implementation in side_effect
        real_subp = subp.subp

        def side_effect(args, *other_args, **kwargs):
            cmd = args[0]
            if cmd not in allow_subp_for:
                raise AssertionError(
                    "Unexpectedly used subp.subp to call {} (allowed:"
                    " {})".format(cmd, ",".join(allow_subp_for))
                )
            return real_subp(args, *other_args, **kwargs)

    with mock.patch("cloudinit.subp.subp", autospec=True) as m_subp:
        m_subp.side_effect = side_effect
        yield
