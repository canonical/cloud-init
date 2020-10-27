import pathlib

import pytest

from cloudinit.stages import _pkl_load
from cloudinit.tests.helpers import resourceLocation


def previous_obj_pkls():
    # This uses paths so we aren't carrying all of these pickles in memory when
    # the tests run
    root = pathlib.Path(resourceLocation("old_pickles"))
    return [
        f for f in root.iterdir() if f.is_file() and f.name.endswith(".pkl")
    ]


@pytest.mark.parametrize(
    "previous_obj_pkl", previous_obj_pkls(), ids=lambda val: val.name
)
class TestUpgrade:
    def test_networking_set_on_distro(self, previous_obj_pkl):
        obj = _pkl_load(str(previous_obj_pkl))
        assert obj.distro.networking is not None

    def test_blacklist_drivers_set_on_networking(self, previous_obj_pkl):
        obj = _pkl_load(str(previous_obj_pkl))
        assert obj.distro.networking.blacklist_drivers is None
