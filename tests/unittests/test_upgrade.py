# Copyright (C) 2020 Canonical Ltd.
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

from cloudinit.sources import pkl_load
from cloudinit.sources.DataSourceAzure import DataSourceAzure
from cloudinit.sources.DataSourceNoCloud import DataSourceNoCloud
from tests.unittests.helpers import resourceLocation

DSNAME_TO_CLASS = {
    "Azure": DataSourceAzure,
    "NoCloud": DataSourceNoCloud,
}


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
        return pkl_load(str(request.param))

    def test_pkl_load_defines_all_init_side_effect_attributes(
        self, previous_obj_pkl
    ):
        """Any attrs as side-effects of __init__ exist in unpickled obj."""
        ds_class = DSNAME_TO_CLASS[previous_obj_pkl.dsname]
        sys_cfg = previous_obj_pkl.sys_cfg
        distro = previous_obj_pkl.distro
        paths = previous_obj_pkl.paths
        ds = ds_class(sys_cfg, distro, paths)
        if ds.dsname == "NoCloud" and previous_obj_pkl.__dict__:
            expected = (
                set({"seed_dirs"}),  # LP: #1568150 handled with getattr checks
                set(),
            )
        else:
            expected = (set(),)
        missing_attrs = ds.__dict__.keys() - previous_obj_pkl.__dict__.keys()
        assert missing_attrs in expected

    def test_networking_set_on_distro(self, previous_obj_pkl):
        """We always expect to have ``.networking`` on ``Distro`` objects."""
        assert previous_obj_pkl.distro.networking is not None

    def test_paths_has_run_dir_attribute(self, previous_obj_pkl):
        assert previous_obj_pkl.paths.run_dir is not None

    def test_vendordata_exists(self, previous_obj_pkl):
        assert previous_obj_pkl.vendordata2 is None
        assert previous_obj_pkl.vendordata2_raw is None
