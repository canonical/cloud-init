# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os

import pytest

from cloudinit import atomic_helper, safeyaml, stages, util
from cloudinit.config.modules import Modules
from cloudinit.settings import PER_INSTANCE
from cloudinit.sources import NetworkConfigSource
from tests.unittests.helpers import replicate_test_root


@pytest.fixture(autouse=True)
def replicate_root(tmp_path):
    replicate_test_root("simple_ubuntu", str(tmp_path))


@pytest.fixture(autouse=True)
def cfg(mocker, tmp_path):
    # root group doesn't exist everywhere
    mocker.patch("cloudinit.util.chownbyname")

    new_root = str(tmp_path)
    _cfg = {
        "datasource_list": ["None"],
        "runcmd": ["ls /etc"],  # test ALL_DISTROS
        "spacewalk": {},  # test non-ubuntu distros module definition
        "system_info": {
            "paths": {"run_dir": new_root},
            "distro": "ubuntu",
        },
        "write_files": [
            {
                "path": "/etc/blah.ini",
                "content": "blah",
                "permissions": 0o755,
            },
        ],
        "cloud_init_modules": ["write_files", "spacewalk", "runcmd"],
    }
    cloud_cfg = safeyaml.dumps(_cfg)
    util.ensure_dir(os.path.join(new_root, "etc", "cloud"))
    util.write_file(
        os.path.join(new_root, "etc", "cloud", "cloud.cfg"), cloud_cfg
    )
    return _cfg


@pytest.mark.usefixtures("fake_filesystem")
class TestSimpleRun:
    def test_none_ds_populates_var_lib_cloud(self):
        """Init and run_section default behavior creates appropriate dirs."""
        # Now start verifying whats created
        netcfg = {
            "version": 1,
            "config": [{"type": "physical", "name": "eth9"}],
        }

        def fake_network_config():
            return netcfg, NetworkConfigSource.FALLBACK

        assert not os.path.exists("/var/lib/cloud")
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        assert os.path.exists("/var/lib/cloud")
        for d in ["scripts", "seed", "instances", "handlers", "sem", "data"]:
            assert os.path.isdir(os.path.join("/var/lib/cloud", d))

        initer.fetch()
        assert not os.path.islink("var/lib/cloud/instance")
        iid = initer.instancify()
        assert iid == "iid-datasource-none"
        initer.update()
        assert os.path.islink("var/lib/cloud/instance")
        initer._find_networking_config = fake_network_config
        assert not os.path.exists(
            "/var/lib/cloud/instance/network-config.json"
        )
        initer.apply_network_config(False)
        assert f"{atomic_helper.json_dumps(netcfg)}\n" == util.load_text_file(
            "/var/lib/cloud/instance/network-config.json"
        )

    def test_none_ds_runs_modules_which_do_not_define_distros(self, caplog):
        """Any modules which do not define a distros attribute are run."""
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )

        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert os.path.exists("/etc/blah.ini")
        assert "write_files" in which_ran
        contents = util.load_text_file("/etc/blah.ini")
        assert contents == "blah"
        assert (
            "Skipping modules ['write_files'] because they are not verified on"
            " distro 'ubuntu'" not in caplog.text
        )

    def test_none_ds_skips_modules_which_define_unmatched_distros(
        self, caplog
    ):
        """Skip modules which define distros which don't match the current."""
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )

        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert (
            "Skipping modules 'spacewalk' because they are not verified on"
            " distro 'ubuntu'" in caplog.text
        )
        assert "spacewalk" not in which_ran

    def test_none_ds_runs_modules_which_distros_all(self, caplog):
        """Skip modules which define distros attribute as supporting 'all'.

        This is done in the module with the declaration:
        distros = [ALL_DISTROS]. runcmd is an example.
        """
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )

        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert "runcmd" in which_ran
        assert (
            "Skipping modules 'runcmd' because they are not verified on"
            " distro 'ubuntu'" not in caplog.text
        )

    def test_none_ds_forces_run_via_unverified_modules(self, caplog, cfg):
        """run_section forced skipped modules by using unverified_modules."""

        # re-write cloud.cfg with unverified_modules override
        cfg = copy.deepcopy(cfg)
        cfg["unverified_modules"] = ["spacewalk"]  # Would have skipped
        cloud_cfg = safeyaml.dumps(cfg)
        util.ensure_dir(os.path.join("/etc", "cloud"))
        util.write_file(os.path.join("/etc", "cloud", "cloud.cfg"), cloud_cfg)

        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )

        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert "spacewalk" in which_ran
        assert "running unverified_modules: 'spacewalk'" in caplog.text

    def test_none_ds_run_with_no_config_modules(self, cfg):
        """run_section will report no modules run when none are configured."""

        # re-write cloud.cfg with unverified_modules override
        cfg = copy.deepcopy(cfg)
        # Represent empty configuration in /etc/cloud/cloud.cfg
        cfg["cloud_init_modules"] = None
        cloud_cfg = safeyaml.dumps(cfg)
        util.ensure_dir(os.path.join("/etc", "cloud"))
        util.write_file(os.path.join("/etc", "cloud", "cloud.cfg"), cloud_cfg)

        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )

        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert [] == which_ran
