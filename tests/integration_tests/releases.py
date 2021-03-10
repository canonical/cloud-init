import functools
import logging
from collections import namedtuple

from packaging import version

from cloudinit.subp import subp, ProcessExecutionError
from tests.integration_tests import integration_settings

log = logging.getLogger('integration_testing')
_image_spec = namedtuple('ImageSpec', 'id, os, release')


def _get_ubuntu_series() -> list:
    """Use distro-info-data's ubuntu.csv to get a list of Ubuntu series"""
    out = ""
    try:
        out, _err = subp(["ubuntu-distro-info", "-a"])
    except ProcessExecutionError:
        log.info(
            "ubuntu-distro-info (from the distro-info package) must be"
            " installed to guess Ubuntu os/release"
        )
    return out.splitlines()


def get_image_from_spec(
    os_image: str = integration_settings.OS_IMAGE
) -> _image_spec:
    """Get the individual parts from an OS_IMAGE definition.

    Returns a namedtuple containing id, os, and release of the image."""
    parts = os_image.split('::', 2)
    image_id = None
    if len(parts) == 1:
        os = 'ubuntu'
        release = parts[0]
        if release not in _get_ubuntu_series():
            raise ValueError(
                'Specified release is not a recognized Ubuntu release')
    elif len(parts) == 3:
        image_id, os, release = parts
    else:
        raise Exception(
            'OS_IMAGE must either contain release name or be in the form '
            'of <image_id>[::<os>[::<release>]]')
    return _image_spec(id=image_id, os=os, release=release)


@functools.total_ordering
class Release:
    _all_releases = []

    def __init__(self, os, name, number):
        self.os = os
        self.name = name
        self.number = number
        Release._all_releases.append(self)

    def __repr__(self):
        return 'Release({}, {}, {})'.format(self.os, self.name, self.number)

    def __lt__(self, other):
        return version.parse(self.number) < version.parse(other.number)

    @classmethod
    def all_releases(cls):
        return cls._all_releases

    @classmethod
    def from_os_image(
        cls, os_image=integration_settings.OS_IMAGE
    ) -> 'Release':
        _, os, release_name = get_image_from_spec(os_image)
        matching_releases = [r for r in cls.all_releases(
        ) if r.os == os and r.name == release_name]
        if len(matching_releases) != 1:
            raise Exception(
                'Expected to find one matching release. '
                'Instead found: {}'.format(matching_releases))
        return matching_releases[0]


XENIAL = Release('ubuntu', 'xenial', '16.04')
BIONIC = Release('ubuntu', 'bionic', '18.04')
FOCAL = Release('ubuntu', 'focal', '20.04')
GROOVY = Release('ubuntu', 'groovy', '20.10')
HIRSUTE = Release('ubuntu', 'hirsuite', '21.04')

UBUNTU = [r for r in Release.all_releases() if r.os == 'ubuntu']
