# This file is part of cloud-init. See LICENSE file for license information.

import tempfile
from unittest import mock

from cloudinit.distros.package_management.paludis import Paludis
from tests.unittests.helpers import CiTestCase

M_PATH = "cloudinit.distros.package_management.paludis.Paludis."
TMP_DIR = tempfile.TemporaryDirectory()


def sanitize_call_args(call_args):
    """
    Since Paludis bases itself on /etc/environment, it might include more
    environment variables than expected. This function filters the call_args
    to only keep the HOME variable in update_env. Only HOME variable
    must be set for Paludis to work.
    """
    args, kwargs = call_args
    new_kwargs = kwargs.copy()

    if "update_env" in new_kwargs and "HOME" in new_kwargs["update_env"]:
        home_value = new_kwargs["update_env"]["HOME"]
        new_kwargs["update_env"] = {"HOME": home_value}

    return mock.call(*args, **new_kwargs)


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

        assert sanitize_call_args(m_subp.call_args) == mock.call(
            **expected_call
        )

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

        assert sanitize_call_args(m_subp.call_args) == mock.call(
            **expected_call
        )

    def test_package_format_full(self, m_subp, m_which):
        # Paludis format: <category>/<name>:<version>::<repo>
        # It can accept shorter versions:
        # <category>/<name>:<version>
        # <category>/<name>
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

        assert sanitize_call_args(m_subp.call_args) == mock.call(
            **expected_call
        )
