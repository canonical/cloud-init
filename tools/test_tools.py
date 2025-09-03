import pathlib
from packaging.version import Version, InvalidVersion
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest import mock

import pytest

# Since read-version has a '-' and no .py extension, we have to do this
# to import it
spec = spec_from_loader(
    "read-version",
    SourceFileLoader(
        "read-version",
        str(pathlib.Path(__file__).absolute().parent / "read-version"),
    ),
)
if not spec:
    pytest.fail("Could not import read-version")
read_version = module_from_spec(spec)
if not spec.loader:
    pytest.fail("Could not import read-version")
spec.loader.exec_module(read_version)


def version_to_pep440(version: str) -> str:
    # read-version can spit out something like 22.4-15-g7f97aee24
    # which is invalid under PEP 440. If we replace the first - with a +
    # that should give us a valid version.
    return version.replace("-", "+", 1)


def assert_valid_version(version):
    try:
        Version(version)
    except InvalidVersion:
        pytest.fail(f"{version} is not PEP 440 compliant")


@pytest.mark.parametrize(
    "version,expected",
    [
        (("23.2", "23.2"), "23.2"),
        (("23.2", "23.2-0-gcdc24d864"), "23.2-0-gcdc24d86"),
        (("23.2.1", "23.2.1"), "23.2.1"),
        (("23.2.1", "23.2.1-0-gcda472559"), "23.2.1-0-gcda47255"),
        (
            ("23.2-65-g392346ccd", "23.2-65-g392346ccd"),
            "23.2-65-g392346cc",
        ),
        (
            ("23.2.1-65-g392346ccd", "23.2.1-65-g392346ccd"),
            "23.2.1-65-g392346cc",
        ),
        (
            (
                "cloud-init-23.1.1-2.el8-2-g285d8d80",
                "cloud-init-23.1.1-2.el8-2-g285d8d80",
            ),
            "23.1.1-2-g285d8d80",
        ),  # RH tags
        (
            (
                "21.1-19-gbad84ad4-0ubuntu1_16.04.4+esm1",
                "21.1-19-gbad84ad4-0ubuntu1_16.04.4+esm1",
            ),
            "21.1-19-gbad84ad4",
        ),
        (("0.3.4ubuntu6", "0.3.4ubuntu6"), "0.3.4"),
        (("noparse", "noparse"), "10.2.1"),
    ],
)
@mock.patch.object(
    read_version.ci_version, "version_string", return_value="10.2.1"
)
class TestReadVersion:
    def test_tag_parsing(self, _m_package_version, version, expected):
        """Ensure that we can parse most tags.

        If  we cannot parse the tag, fallback to package version.
        """
        with mock.patch.object(
            read_version, "get_version_from_git", return_value=version
        ):
            out = read_version.main()
        assert out == expected

        # Also ensure it passes setuptools PEP 440 check
        assert_valid_version(version_to_pep440(out))
