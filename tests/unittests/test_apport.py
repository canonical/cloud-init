import os
import sys
from importlib import reload

import pytest

from cloudinit import apport
from tests.unittests.helpers import mock

M_PATH = "cloudinit.apport."


@pytest.fixture
def m_hookutils():
    m_hookutils = mock.Mock()
    with mock.patch.dict(sys.modules, {"apport.hookutils": m_hookutils}):
        reload(sys.modules["cloudinit.apport"])
        yield m_hookutils
    reload(sys.modules["cloudinit.apport"])


class TestApport:
    def test_can_attach_sensitive(self):
        ui = mock.Mock()

        ui.yesno.return_value = True
        assert apport.can_attach_sensitive(object(), ui) is True

        ui.yesno.return_value = False
        assert apport.can_attach_sensitive(object(), ui) is False

        ui.yesno.return_value = None

        with pytest.raises(StopIteration):
            apport.can_attach_sensitive(object(), ui)

    @pytest.mark.parametrize("include_sensitive", (True, False))
    def test_attach_cloud_init_logs(
        self, include_sensitive, mocker, m_hookutils
    ):
        mocker.patch(f"{M_PATH}attach_root_command_outputs")
        mocker.patch(f"{M_PATH}attach_file")
        m_root_command = mocker.patch(f"{M_PATH}root_command_output")
        apport.attach_cloud_init_logs(
            object(), include_sensitive=include_sensitive
        )
        if include_sensitive:
            m_root_command.assert_called_once_with(
                [
                    "cloud-init",
                    "collect-logs",
                    "-t",
                    "/tmp/cloud-init-logs.tgz",
                ]
            )
        else:
            m_root_command.assert_called_once_with(
                [
                    "cloud-init",
                    "collect-logs",
                    "-t",
                    "/tmp/cloud-init-logs.tgz",
                    "--redact",
                ]
            )

    @pytest.mark.parametrize(
        "report,tags",
        (
            ({"Irrelevant": "."}, ""),
            ({"UdiLog": "."}, "ubuntu-desktop-installer"),
            ({"CurtinError": ".", "SubiquityLog": "."}, "curtin subiquity"),
            (
                {
                    "UdiLog": ".",
                    "JournalErrors": "...Breaking ordering cycle...",
                },
                "systemd-ordering ubuntu-desktop-installer",
            ),
        ),
    )
    def test_add_bug_tags_assigns_proper_tags(self, report, tags):
        """Tags are assigned based on non-empty project report key values."""

        apport.add_bug_tags(report)
        assert report.get("Tags", "") == tags

    @mock.patch(M_PATH + "os.path.exists", return_value=True)
    def test_attach_ubuntu_pro_info(self, m_exists, m_hookutils):
        report = {}
        apport.attach_ubuntu_pro_info(report)

        assert [
            mock.call(
                report, os.path.realpath("/var/log/ubuntu-advantage.log")
            ),
        ] == m_hookutils.attach_file_if_exists.call_args_list
        assert report.get("Tags", "") == "ubuntu-pro"

    @mock.patch(M_PATH + "os.path.exists", return_value=False)
    def test_attach_ubuntu_pro_info_log_non_present(
        self, m_exists, m_hookutils
    ):
        report = {}
        apport.attach_ubuntu_pro_info(report)

        assert [
            mock.call(
                report, os.path.realpath("/var/log/ubuntu-advantage.log")
            ),
        ] == m_hookutils.attach_file_if_exists.call_args_list
        assert report.get("Tags", "") == ""
