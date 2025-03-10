# This file is part of cloud-init. See LICENSE file for license information.

import tempfile
from unittest import mock

from cloudinit.distros.package_management.paludis import (
    Paludis,
)
from tests.unittests.helpers import CiTestCase

M_PATH = "cloudinit.distros.package_management.paludis.Paludis."
TMP_DIR = tempfile.TemporaryDirectory()


@mock.patch.dict("os.environ", {}, clear=True)
@mock.patch("cloudinit.distros.debian.subp.which", return_value=True)
@mock.patch("cloudinit.distros.debian.subp.subp")
class TestPaludisCommand(CiTestCase):
    def test_sync_command(self, m_subp, m_which):
        paludis = Paludis(
            runner=mock.Mock(),
            cave_command=["eatmydata"],
            cave_sync_subcommand=["sync-world"],
        )
        paludis.run_package_command("sync")
        expected_call = {
            "args": ["eatmydata", "sync-world"],
            "capture": False,
            "update_env": {
                "HOME": "/tmp",
            },
        }
        assert m_subp.call_args == mock.call(**expected_call)

    def test_upgrade_command(self, m_subp, m_which):
        paludis = Paludis(
            runner=mock.Mock(),
            cave_command=["eatmydata"],
            cave_system_upgrade_subcommand=["upgrade-system"],
        )
        paludis.run_package_command("upgrade")
        expected_call = {
            "args": ["eatmydata", "upgrade-system"],
            "capture": False,
            "update_env": {
                "HOME": "/tmp",
            },
        }
        assert m_subp.call_args == mock.call(**expected_call)

    def test_package_format_full(self, m_subp, m_which):
        package = "net/netcat-openbsd:0.2::private-repo"
        paludis = Paludis(runner=mock.Mock(), cave_command=["eatmydata"])
        paludis.install_packages([package])
        expected_call = {
            "args": ["eatmydata", "resolve", "-x", package],
            "capture": False,
            "update_env": {
                "HOME": "/tmp",
            },
        }
        assert m_subp.call_args == mock.call(**expected_call)
