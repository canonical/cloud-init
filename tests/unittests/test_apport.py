import os
import sys
from importlib import reload

import pytest

from cloudinit import apport
from tests.unittests.helpers import mock

M_PATH = "cloudinit.apport."


class TestApport:
    @pytest.mark.parametrize(
        "instance_data,choice_idx,expected_report",
        (
            pytest.param(
                '{"v1": {"cloud_name": "mycloud"}}',
                None,
                {},
                id="v1_cloud_name_exists",
            ),
            pytest.param(
                '{"v1": {"cloud_id": "invalid"}}',
                1,
                {"CloudName": "Azure"},
                id="v1_no_cloud_name_present",
            ),
            pytest.param("{}", 0, {"CloudName": "AliYun"}, id="no_v1_key"),
            pytest.param(
                "{", 22, {"CloudName": "Oracle"}, id="not_valid_json"
            ),
        ),
    )
    def test_attach_cloud_info(
        self, instance_data, choice_idx, expected_report, mocker, paths
    ):
        """Prompt for cloud name when instance-data.json is not-json/absent."""
        mocker.patch(M_PATH + "read_cfg_paths", return_value=paths)
        instance_data_file = paths.get_runpath("instance_data")
        if instance_data is None:
            assert not os.path.exists(instance_data_file)
        else:
            with open(instance_data_file, "w") as stream:
                stream.write(instance_data)
        ui = mock.Mock()
        ui.yesno.return_value = True
        ui.choice.return_value = (choice_idx, "")
        report = {}
        apport.attach_cloud_info(report, ui)
        if choice_idx is not None:
            assert ui.choice.call_count == 1
            assert report["CloudName"] == apport.KNOWN_CLOUD_NAMES[choice_idx]
        else:
            assert ui.choice.call_count == 0

    def test_attach_user_data(self, mocker, paths):
        user_data_file = paths.get_ipath_cur("userdata_raw")
        ui = mock.Mock()
        ui.yesno.return_value = True
        report = object()
        m_hookutils = mock.Mock()

        with mock.patch.dict(sys.modules, {"apport.hookutils": m_hookutils}):
            reload(sys.modules["cloudinit.apport"])
            mocker.patch(M_PATH + "read_cfg_paths", return_value=paths)
        apport.attach_user_data(report, ui)
        assert [
            mock.call(report, user_data_file, "user_data.txt"),
        ] == apport.attach_file.call_args_list
        assert [
            mock.call(
                report,
                "/var/log/installer/autoinstall-user-data",
                "AutoInstallUserData",
            ),
            mock.call(report, "/autoinstall.yaml", "AutoInstallYAML"),
            mock.call(
                report,
                "/etc/cloud/cloud.cfg.d/99-installer.cfg",
                "InstallerCloudCfg",
            ),
        ] == apport.attach_file_if_exists.call_args_list

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
    def test_attach_ubuntu_pro_info(self, m_exists):
        m_hookutils = mock.Mock()
        with mock.patch.dict(sys.modules, {"apport.hookutils": m_hookutils}):
            reload(sys.modules["cloudinit.apport"])
            report = {}
            apport.attach_ubuntu_pro_info(report)

        assert [
            mock.call(report, "/var/log/ubuntu-advantage.log"),
        ] == m_hookutils.attach_file_if_exists.call_args_list
        assert report.get("Tags", "") == "ubuntu-pro"

    @mock.patch(M_PATH + "os.path.exists", return_value=False)
    def test_attach_ubuntu_pro_info_log_non_present(self, m_exists):
        m_hookutils = mock.Mock()
        with mock.patch.dict(sys.modules, {"apport.hookutils": m_hookutils}):
            reload(sys.modules["cloudinit.apport"])
            report = {}
            apport.attach_ubuntu_pro_info(report)

        assert [
            mock.call(report, "/var/log/ubuntu-advantage.log"),
        ] == m_hookutils.attach_file_if_exists.call_args_list
        assert report.get("Tags", "") == ""
