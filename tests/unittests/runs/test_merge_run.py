# This file is part of cloud-init. See LICENSE file for license information.

import os

import pytest

from cloudinit import safeyaml, stages, util
from cloudinit.config.modules import Modules
from cloudinit.settings import PER_INSTANCE
from tests.unittests import helpers
from tests.unittests.helpers import replicate_test_root


@pytest.fixture(autouse=True)
def user_data(tmp_path):
    replicate_test_root("simple_ubuntu", str(tmp_path))
    return helpers.readResource("user_data.1.txt")


@pytest.fixture(autouse=True)
def cfg(tmp_path, mocker):
    mocker.patch("cloudinit.util.os.chown")
    new_root = str(tmp_path)
    cfg = {
        "datasource_list": ["None"],
        "cloud_init_modules": ["write_files"],
        "system_info": {
            "paths": {"run_dir": new_root},
            "package_mirrors": [
                {
                    "arches": ["i386", "amd64", "blah"],
                    "failsafe": {
                        "primary": "http://my.archive.mydomain.com/ubuntu",
                        "security": ("http://my.security.mydomain.com/ubuntu"),
                    },
                    "search": {"primary": [], "security": []},
                },
            ],
        },
    }
    cloud_cfg = safeyaml.dumps(cfg)
    util.ensure_dir(os.path.join(new_root, "etc", "cloud"))
    util.write_file(
        os.path.join(new_root, "etc", "cloud", "cloud.cfg"), cloud_cfg
    )


@pytest.mark.usefixtures("fake_filesystem")
class TestMergeRun:
    def test_none_ds(self, user_data):
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.datasource.userdata_raw = user_data
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mirrors = initer.distro.get_option("package_mirrors")
        assert 1 == len(mirrors)
        mirror = mirrors[0]
        assert mirror["arches"] == ["i386", "amd64", "blah"]
        mods = Modules(initer)
        (which_ran, failures) = mods.run_section("cloud_init_modules")
        assert not failures
        assert os.path.exists("/etc/blah.ini")
        assert "write_files" in which_ran
        contents = util.load_text_file("/etc/blah.ini")
        assert contents == "blah"
