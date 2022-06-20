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
            mock.call(report, user_data_file, "user_data.txt")
        ] == m_hookutils.attach_file.call_args_list
