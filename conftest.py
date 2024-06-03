"""Global conftest.py

This conftest is used for unit tests in ``cloudinit/`` and ``tests/unittests/``
as well as the integration tests in ``tests/integration_tests/``.

Any imports that are performed at the top-level here must be installed wherever
any of these tests run: that is to say, they must be listed in
``integration-requirements.txt`` and in ``test-requirements.txt``.
"""
# If we don't import this early, lru_cache may get applied before we have the
# chance to patch. This is also too early for the pytest-antilru plugin
# to work.
# isort: off
from tests.unittests.early_patches import get_cached_functions  # noqa: E402

# isort: on
from unittest import mock

import pytest

from cloudinit import helpers, subp, util


@pytest.fixture(autouse=True, scope="function")
def cleanup_lru_cache():
    yield

    for func in get_cached_functions():
        func.cache_clear()


class _FixtureUtils:
    """A namespace for fixture helper functions, used by fixture_utils.

    These helper functions are all defined as staticmethods so they are
    effectively functions; they are defined in a class only to give us a
    namespace so calling them can look like
    ``fixture_utils.fixture_util_function()`` in test code.
    """

    @staticmethod
    def closest_marker_args_or(request, marker_name: str, default):
        """Get the args for closest ``marker_name`` or return ``default``

        :param request:
            A pytest request, as passed to a fixture.
        :param marker_name:
            The name of the marker to look for
        :param default:
            The value to return if ``marker_name`` is not found.

        :return:
            The args for the closest ``marker_name`` marker, or ``default``
            if no such marker is found.
        """
        try:
            marker = request.node.get_closest_marker(marker_name)
        except AttributeError:
            # Older versions of pytest don't have the new API
            marker = request.node.get_marker(marker_name)
        if marker is not None:
            return marker.args
        return default

    @staticmethod
    def closest_marker_first_arg_or(request, marker_name: str, default):
        """Get the first arg for closest ``marker_name`` or return ``default``

        This is a convenience wrapper around closest_marker_args_or, see there
        for full details.
        """
        result = _FixtureUtils.closest_marker_args_or(
            request, marker_name, [default]
        )
        if not result:
            raise TypeError(
                "Missing expected argument to {} marker".format(marker_name)
            )
        return result[0]


class UnexpectedSubpError(BaseException):
    """Error thrown when subp.subp is unexpectedly used.

    We inherit from BaseException so it doesn't get silently swallowed
    by other error handlers.
    """


@pytest.fixture(autouse=True)
def disable_subp_usage(request, fixture_utils):
    """
    Across all (pytest) tests, ensure that subp.subp is not invoked.

    Note that this can only catch invocations where the ``subp`` module is
    imported and ``subp.subp(...)`` is called.  ``from cloudinit.subp import
    subp`` imports happen before the patching here (or the CiTestCase
    monkey-patching) happens, so are left untouched.

    While ``disable_subp_usage`` unconditionally patches
    ``cloudinit.subp.subp``, any test-local patching will override this
    patching (i.e. the mock created for that patch call will replace the mock
    created by ``disable_subp_usage``), allowing tests to be written normally.
    One important exception: if ``autospec=True`` is passed to such an
    overriding patch call it will fail: autospeccing introspects the object
    being patched and as ``subp.subp`` will always be a mock when that
    autospeccing happens, the introspection fails.  (The specific error is:
    ``TypeError: name must be a str, not a MagicMock``.)

    To allow a particular test method or class to use ``subp.subp`` you can
    mark it as such::

        @pytest.mark.allow_all_subp
        def test_whoami(self):
            subp.subp(["whoami"])

    To instead allow ``subp.subp`` usage for a specific command, you can use
    the ``allow_subp_for`` mark::

        @pytest.mark.allow_subp_for("bash")
        def test_bash(self):
            subp.subp(["bash"])

    You can pass multiple commands as values; they will all be permitted::

        @pytest.mark.allow_subp_for("bash", "whoami")
        def test_several_things(self):
            subp.subp(["bash"])
            subp.subp(["whoami"])

    This fixture (roughly) mirrors the functionality of
    ``CiTestCase.allowed_subp``.  N.B. While autouse fixtures do affect
    non-pytest tests, CiTestCase's ``allowed_subp`` does take precedence (and
    we have ``TestDisableSubpUsageInTestSubclass`` to confirm that).
    """
    allow_subp_for = fixture_utils.closest_marker_args_or(
        request, "allow_subp_for", None
    )
    # Because the mark doesn't take arguments, `allow_all_subp` will be set to
    # [] if the marker is present, so explicit None checks are required
    allow_all_subp = fixture_utils.closest_marker_args_or(
        request, "allow_all_subp", None
    )

    if allow_all_subp is not None and allow_subp_for is None:
        # Only allow_all_subp specified, don't mock subp.subp
        yield
        return

    if allow_all_subp is None and allow_subp_for is None:
        # No marks, default behaviour; disallow all subp.subp usage
        def side_effect(args, *other_args, **kwargs):
            raise UnexpectedSubpError("Unexpectedly used subp.subp")

    elif allow_all_subp is not None and allow_subp_for is not None:
        # Both marks, ambiguous request; raise an exception on all subp usage
        def side_effect(args, *other_args, **kwargs):
            raise UnexpectedSubpError(
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
                raise UnexpectedSubpError(
                    "Unexpectedly used subp.subp to call {} (allowed:"
                    " {})".format(cmd, ",".join(allow_subp_for))
                )
            return real_subp(args, *other_args, **kwargs)

    with mock.patch("cloudinit.subp.subp", autospec=True) as m_subp:
        m_subp.side_effect = side_effect
        yield


@pytest.fixture(scope="session")
def fixture_utils():
    """Return a namespace containing fixture utility functions.

    See :py:class:`_FixtureUtils` for further details."""
    return _FixtureUtils


@pytest.fixture
def mocked_responses():
    import responses as _responses

    with _responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def paths(tmpdir):
    """
    Return a helpers.Paths object configured to use a tmpdir.

    (This uses the builtin tmpdir fixture.)
    """
    dirs = {
        "cloud_dir": tmpdir.mkdir("cloud_dir").strpath,
        "docs_dir": tmpdir.mkdir("docs_dir").strpath,
        "run_dir": tmpdir.mkdir("run_dir").strpath,
    }
    return helpers.Paths(dirs)


@pytest.fixture(autouse=True, scope="session")
def monkeypatch_system_info():
    def my_system_info():
        return {
            "platform": "invalid",
            "system": "invalid",
            "release": "invalid",
            "python": "invalid",
            "uname": ["invalid"] * 6,
            "dist": ("Distro", "-1.1", "Codename"),
            "variant": "ubuntu",
        }

    util.system_info = my_system_info
