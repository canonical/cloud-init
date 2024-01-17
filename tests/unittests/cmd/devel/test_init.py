from unittest import mock

from cloudinit import stages
from cloudinit.cmd.devel import read_cfg_paths
from tests.unittests.util import TEST_INSTANCE_ID, FakeDataSource


class TestReadCfgPaths:
    def test_read_cfg_paths_fetches_cached_datasource(self, tmpdir):
        init = stages.Init()
        init._cfg = {
            "system_info": {
                "distro": "ubuntu",
                "paths": {"cloud_dir": tmpdir, "run_dir": tmpdir},
            }
        }
        with mock.patch("cloudinit.cmd.devel.Init") as m_init:
            with mock.patch.object(init, "_restore_from_cache") as restore:
                restore.return_value = FakeDataSource(paths=init.paths)
                with mock.patch(
                    "cloudinit.util.read_conf_from_cmdline", return_value={}
                ), mock.patch("cloudinit.util.read_conf", return_value={}):
                    m_init.return_value = init
                    paths = read_cfg_paths()
                    assert paths.get_ipath() is None
                    paths = read_cfg_paths(fetch_existing_datasource="trust")
        assert (
            paths.get_ipath() == f"/var/lib/cloud/instances/{TEST_INSTANCE_ID}"
        )
