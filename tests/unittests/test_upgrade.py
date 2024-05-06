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
from unittest import mock

import pytest

from cloudinit import importer, settings, sources, type_utils
from cloudinit.sources.DataSourceAzure import DataSourceAzure
from cloudinit.sources.DataSourceNoCloud import DataSourceNoCloud
from tests.unittests.helpers import resourceLocation
from tests.unittests.util import MockDistro

DSNAME_TO_CLASS = {
    "Azure": DataSourceAzure,
    "NoCloud": DataSourceNoCloud,
}


class TestUpgrade:
    # Expect the following "gaps" in unpickling per-datasource.
    # The presence of these attributes existed in 20.1.
    ds_expected_unpickle_attrs = {
        "AltCloud": {"seed", "supported_seed_starts"},
        "AliYun": {"identity", "metadata_address", "default_update_events"},
        "Azure": {
            "_ephemeral_dhcp_ctx",
            "_iso_dev",
            "_network_config",
            "_reported_ready_marker_file",
            "_route_configured_for_imds",
            "_route_configured_for_wireserver",
            "_wireserver_endpoint",
            "cfg",
            "seed",
            "seed_dir",
        },
        "CloudSigma": {"cepko", "ssh_public_key"},
        "CloudStack": {
            "api_ver",
            "cfg",
            "metadata_address",
            "seed_dir",
            "vr_addr",
        },
        "ConfigDrive": {
            "_network_config",
            "ec2_metadata",
            "files",
            "known_macs",
            "network_eni",
            "network_json",
            "seed_dir",
            "source",
            "version",
        },
        "DigitalOcean": {
            "_network_config",
            "metadata_address",
            "metadata_full",
            "retries",
            "timeout",
            "use_ip4LL",
            "wait_retry",
        },
        "Ec2": {"identity", "metadata_address"},
        "Exoscale": {
            "api_version",
            "extra_config",
            "metadata_url",
            "password_server_port",
            "url_retries",
            "url_timeout",
        },
        "GCE": {"default_user", "metadata_address"},
        "Hetzner": {
            "_network_config",
            "dsmode",
            "metadata_address",
            "metadata_full",
            "retries",
            "timeout",
            "userdata_address",
            "wait_retry",
        },
        "IBMCloud": {"source", "_network_config", "network_json", "platform"},
        "RbxCloud": {"cfg", "gratuitous_arp", "seed"},
        "Scaleway": {
            "_network_config",
            "metadata_url",
            "retries",
            "timeout",
        },
        "Joyent": {
            "_network_config",
            "network_data",
            "routes_data",
            "script_base_d",
        },
        "MAAS": {"base_url", "seed_dir"},
        "NoCloud": {
            "_network_eni",
            "_network_config",
            "supported_seed_starts",
            "seed_dir",
            "seed",
            "seed_dirs",
        },
        "NWCS": {
            "_network_config",
            "dsmode",
            "metadata_address",
            "metadata_full",
            "retries",
            "timeout",
            "wait_retry",
        },
        "OpenNebula": {"network", "seed", "seed_dir"},
        "OpenStack": {
            "ec2_metadata",
            "files",
            "metadata_address",
            "network_json",
            "ssl_details",
            "version",
        },
        "OVF": {
            "cfg",
            "environment",
            "_network_config",
            "seed",
            "seed_dir",
            "supported_seed_starts",
        },
        "UpCloud": {
            "_network_config",
            "metadata_address",
            "metadata_full",
            "retries",
            "timeout",
            "wait_retry",
        },
        "Vultr": {"netcfg"},
        "VMware": {
            "data_access_method",
            "rpctool",
            "rpctool_fn",
        },
        "WSL": {"instance_name"},
    }

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
        return sources.pkl_load(str(request.param))

    @pytest.mark.parametrize(
        "mode",
        (
            [sources.DEP_FILESYSTEM],
            [sources.DEP_FILESYSTEM, sources.DEP_NETWORK],
        ),
    )
    @mock.patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    @mock.patch(
        "cloudinit.sources.DataSourceCloudStack.get_vr_address",
        return_value="data-server.",
    )
    def test_all_ds_init_vs_unpickle_attributes(
        self, m_get_vr_address, mode, mocker, paths, tmpdir
    ):
        """Unpickle resets any instance attributes created in __init__

        This test asserts that deserialization of a datasource cache
        does proper initialization of any 'new' instance attributes
        created as a side-effect of the __init__ method.

        Without proper _unpickle coverage for newly introduced attributes,
        the new deserialized instance will hit AttributeErrors at runtime.
        """
        # Load all cloud-init init-local time-frame DataSource classes
        for ds_class in sources.list_sources(
            settings.CFG_BUILTIN["datasource_list"],
            mode,
            [type_utils.obj_name(sources)],
        ):
            # Expected common instance attrs from __init__ that are typically
            # handled via existing _unpickling and setup in _get_data
            common_instance_attrs = {
                "paths",
                "vendordata2",
                "sys_cfg",
                "ud_proc",
                "vendordata",
                "vendordata2_raw",
                "ds_cfg",
                "distro",
                "userdata",
                "userdata_raw",
                "metadata",
                "vendordata_raw",
            }
            # Grab initial specific-class attributes from magic method
            class_attrs = set(ds_class.__dict__)

            # Mock known subp calls from some datasource __init__ setup
            mocker.patch("cloudinit.util.is_container", return_value=False)
            mocker.patch("cloudinit.dmi.read_dmi_data", return_value="")
            mocker.patch("cloudinit.subp.subp", return_value=("", ""))

            # Initialize the class to grab the instance attributes from
            # instance.__dict__ magic method.
            ds = ds_class(sys_cfg={}, distro=MockDistro(), paths=paths)

            if getattr(ds.__class__.__bases__[0], "dsname", None) == ds.dsname:
                # We are a subclass in a different boot mode (Local/Net) and
                # share a common parent with class atttributes
                class_attrs.update(ds.__class__.__bases__[0].__dict__)

            # Determine new instance attributes created by __init__
            # by calling the __dict__ magic method on the instance.
            # Then, subtract common_instance_attrs and
            # ds_expected_unpickle_attrs from the list of current attributes.
            # What's left is our 'new' instance attributes added as a
            # side-effect of __init__.
            init_attrs = (
                set(ds.__dict__)
                - class_attrs
                - common_instance_attrs
                - self.ds_expected_unpickle_attrs.get(ds_class.dsname, set())
            )

            # Remove all side-effect attributes added by __init__
            for side_effect_attr in init_attrs:
                delattr(ds, side_effect_attr)

            # Pickle the version of the DataSource with all init_attrs removed
            sources.pkl_store(ds, tmpdir.join(f"{ds.dsname}.obj.pkl"))

            # Reload the pickled bare-bones datasource to ensure all instance
            # attributes are reconstituted by _unpickle helpers.
            ds2 = sources.pkl_load(tmpdir.join(f"{ds.dsname}.obj.pkl"))
            unpickled_attrs = (
                set(ds2.__dict__) - class_attrs - common_instance_attrs
            )
            missing_unpickled_attrs = init_attrs - unpickled_attrs
            assert not missing_unpickled_attrs, (
                f"New {ds_class.dsname} attributes need unpickle coverage:"
                f" {missing_unpickled_attrs}"
            )

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
            # seed_dirs is covered by _unpickle
            # _network_config and _network_eni were already initialized
            # outside of __init__ so shouldn't need unpickling
            expected = {"seed_dirs", "_network_config", "_network_eni"}
        else:
            expected = (set(),)
        missing_attrs = ds.__dict__.keys() - previous_obj_pkl.__dict__.keys()
        for attr in missing_attrs:
            assert attr in expected

    def test_networking_set_on_distro(self, previous_obj_pkl):
        """We always expect to have ``.networking`` on ``Distro`` objects."""
        assert previous_obj_pkl.distro.networking is not None

    def test_paths_has_run_dir_attribute(self, previous_obj_pkl):
        assert previous_obj_pkl.paths.run_dir is not None

    def test_vendordata_exists(self, previous_obj_pkl):
        assert previous_obj_pkl.vendordata2 is None
        assert previous_obj_pkl.vendordata2_raw is None
