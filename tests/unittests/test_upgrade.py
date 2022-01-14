# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Upgrade testing for cloud-init.

This module tests cloud-init's behaviour across upgrades.  Specifically, it
specifies a set of invariants that the current codebase expects to be true (as
tests in ``TestUpgrade``) and then checks that these hold true after unpickling
``obj.pkl``s from previous versions of cloud-init; those pickles are stored in
``tests/data/old_pickles/``.
"""

import operator
import pathlib

import pytest

from cloudinit.stages import _pkl_load
from tests.unittests.helpers import resourceLocation


class TestUpgrade:
    @pytest.fixture(
        params=pathlib.Path(resourceLocation("old_pickles")).glob("*.pkl"),
        scope="class",
        ids=operator.attrgetter("name"),
    )
    def previous_obj_pkl(self, request):
        """Load each pickle to memory once, then run all tests against it.

        Test implementations _must not_ modify the ``previous_obj_pkl`` which
        they are passed, as that will affect tests that run after them.
        """
        return _pkl_load(str(request.param))

    def test_networking_set_on_distro(self, previous_obj_pkl):
        """We always expect to have ``.networking`` on ``Distro`` objects."""
        assert previous_obj_pkl.distro.networking is not None

    def test_blacklist_drivers_set_on_networking(self, previous_obj_pkl):
        """We always expect Networking.blacklist_drivers to be initialised."""
        assert previous_obj_pkl.distro.networking.blacklist_drivers is None

    def test_paths_has_run_dir_attribute(self, previous_obj_pkl):
        assert previous_obj_pkl.paths.run_dir is not None

    def test_vendordata_exists(self, previous_obj_pkl):
        assert previous_obj_pkl.vendordata2 is None
        assert previous_obj_pkl.vendordata2_raw is None
