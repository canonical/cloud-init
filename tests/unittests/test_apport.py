import os

import pytest

from tests.unittests.helpers import mock

M_PATH = "cloudinit.apport."


@pytest.fixture()
def apport(request, mocker, paths):
    """Mock apport.hookutils before importing cloudinit.apport.

    This avoids our optional import dependency on apport, providing tests with
    mocked apport.hookutils function call counts.
    """
    m_hookutils = mock.Mock()
    mocker.patch.dict("sys.modules", {"apport.hookutils": m_hookutils})
    mocker.patch(M_PATH + "read_cfg_paths", return_value=paths)
    from cloudinit import apport

    yield apport


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
        self, instance_data, choice_idx, expected_report, apport, paths
    ):
        """Prompt for cloud name when instance-data.json is not-json/absent."""

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

    def test_attach_user_data(self, apport, paths):
        user_data_file = paths.get_ipath_cur("userdata_raw")
        ui = mock.Mock()
        ui.yesno.return_value = True
        report = object()
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
    def test_add_bug_tags_assigns_proper_tags(self, report, tags, apport):
        """Tags are assigned based on non-empty project report key values."""

        apport.add_bug_tags(report)
        assert report.get("Tags", "") == tags
