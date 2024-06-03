import functools
import logging
from typing import Optional

from packaging import version

from cloudinit import subp
from tests.integration_tests import integration_settings

log = logging.getLogger("integration_testing")


def ubuntu_version_from_series(series) -> str:
    running_ubuntu = subp.which("ubuntu-distro-info")
    try:
        out = subp.subp(
            ["ubuntu-distro-info", "--release", "--series", series]
        ).stdout
    except subp.ProcessExecutionError as e:
        if not running_ubuntu:
            log.info(
                "ubuntu-distro-info (from the distro-info package) not "
                " installed, attempting pass through Ubuntu os/release"
            )
            return series
        raise ValueError(
            f"'{series}' is not a recognized Ubuntu release"
        ) from e
    return out.strip().rstrip(" LTS")


@functools.total_ordering
class Release:
    def __init__(
        self,
        os: str,
        series: str,
        version: str,
        image_id: Optional[str] = None,
    ):
        self.os = os
        self.series = series
        self.version = version
        self.image_id = image_id

    def __repr__(self):
        return f"Release({self.os}, {self.version})"

    def __eq__(self, other: object):
        if not isinstance(other, Release):
            return False
        if all(
            [
                self.os == other.os,
                self.series == other.series,
                self.version == other.version,
            ]
        ):
            if self.image_id and other.image_id:
                return self.image_id == other.image_id
            return True  # If either image_id is None then ignore it
        return False

    def __lt__(self, other: "Release"):
        if self.os != other.os:
            raise ValueError(f"{self.os} cannot be compared to {other.os}!")
        return version.parse(self.version) < version.parse(other.version)

    @classmethod
    def from_os_image(
        cls,
        os_image: str = integration_settings.OS_IMAGE,
    ) -> "Release":
        """Get the individual parts from an OS_IMAGE definition.

        Returns a namedtuple containing id, os, and release of the image."""
        parts = os_image.split("::", 3)
        if len(parts) == 1:
            image_id = None
            os = "ubuntu"
            series = parts[0]
            version = ubuntu_version_from_series(series)
        elif len(parts) == 4:
            image_id, os, series, version = parts
        else:
            raise ValueError(
                "OS_IMAGE must either contain release name or be in the form "
                "of <image_id>[::<os>::<release>::<version>]"
            )
        return cls(os, series, version, image_id)


BIONIC = Release("ubuntu", "bionic", "18.04")
FOCAL = Release("ubuntu", "focal", "20.04")
JAMMY = Release("ubuntu", "jammy", "22.04")
KINETIC = Release("ubuntu", "kinetic", "22.10")
LUNAR = Release("ubuntu", "lunar", "23.04")
MANTIC = Release("ubuntu", "mantic", "23.10")
NOBLE = Release("ubuntu", "noble", "24.04")
ORACULAR = Release("ubuntu", "oracular", "24.10")

UBUNTU_STABLE = (FOCAL, JAMMY, MANTIC, NOBLE)

CURRENT_RELEASE = Release.from_os_image()
IS_UBUNTU = CURRENT_RELEASE.os == "ubuntu"
