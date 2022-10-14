import pytest

from tests.unittests.helpers import mock

M_PATH = "cloudinit.apport."


class TestApport:
    def test_attach_user_data(self, mocker, tmpdir):
        m_hookutils = mock.Mock()
        mocker.patch.dict("sys.modules", {"apport.hookutils": m_hookutils})
        user_data_file = tmpdir.join("instance", "user-data.txt")
        mocker.patch(
            M_PATH + "_get_user_data_file", return_value=user_data_file
        )

        from cloudinit import apport

        ui = mock.Mock()
        ui.yesno.return_value = True
        report = object()
        apport.attach_user_data(report, ui)
        assert [
            mock.call(report, user_data_file, "user_data.txt"),
        ] == m_hookutils.attach_file.call_args_list
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
        ] == m_hookutils.attach_file_if_exists.call_args_list

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
        from cloudinit import apport

        apport.add_bug_tags(report)
        assert report.get("Tags", "") == tags
