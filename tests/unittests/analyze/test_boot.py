import os

import pytest

from cloudinit.analyze import analyze_boot, get_parser
from cloudinit.analyze.show import (
    CONTAINER_CODE,
    FAIL_CODE,
    SUCCESS_CODE,
    SystemctlReader,
    dist_check_timestamp,
    gather_timestamps_using_systemd,
)
from tests.unittests.helpers import mock

err_code = (FAIL_CODE, -1, -1, -1)


class TestDistroChecker:
    @mock.patch("cloudinit.subp.subp")
    def test_blank_distro(self, m_subp):
        assert err_code == dist_check_timestamp()

    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.is_FreeBSD", return_value=True)
    def test_freebsd_gentoo_cant_find(self, m_is_FreeBSD, m_subp):
        err_code == dist_check_timestamp()

    @mock.patch("cloudinit.subp.subp", return_value=(0, 1))
    def test_subp_fails(self, m_subp):
        assert err_code == dist_check_timestamp()


class TestSystemCtlReader:
    def test_systemctl_invalid(self, mocker):
        mocker.patch(
            "cloudinit.analyze.show.subp.subp",
            return_value=("", "something_invalid"),
        )
        reader = SystemctlReader("dont", "care")
        with pytest.raises(RuntimeError):
            reader.parse_epoch_as_float()

    @mock.patch("cloudinit.subp.subp", return_value=("U=1000000", None))
    def test_systemctl_works_correctly_threshold(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        assert 1.0 == reader.parse_epoch_as_float()
        thresh = 1.0 - reader.parse_epoch_as_float()
        assert thresh < 1e-6
        assert thresh > (-1 * 1e-6)

    @mock.patch("cloudinit.subp.subp", return_value=("U=0", None))
    def test_systemctl_succeed_zero(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        assert 0.0 == reader.parse_epoch_as_float()

    @mock.patch("cloudinit.subp.subp", return_value=("U=1", None))
    def test_systemctl_succeed_distinct(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        val1 = reader.parse_epoch_as_float()
        m_subp.return_value = ("U=2", None)
        reader2 = SystemctlReader("dummyProperty", "dummyParameter")
        val2 = reader2.parse_epoch_as_float()
        assert val1 != val2

    @pytest.mark.parametrize(
        "return_value, exception",
        [
            pytest.param(("100", None), IndexError, id="epoch_not_splittable"),
            pytest.param(
                ("U=foobar", None),
                ValueError,
                id="cannot_convert_epoch_to_float",
            ),
        ],
    )
    @mock.patch("cloudinit.subp.subp")
    def test_systemctl_epoch_not_error(self, m_subp, return_value, exception):
        m_subp.return_value = return_value
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        with pytest.raises(exception):
            reader.parse_epoch_as_float()


class TestAnalyzeBoot:
    def set_up_dummy_file_ci(self, path, log_path):
        infh = open(path, "w+")
        infh.write(
            "2019-07-08 17:40:49,601 - util.py[DEBUG]: Cloud-init v. "
            "19.1-1-gbaa47854-0ubuntu1~18.04.1 running 'init-local' "
            "at Mon, 08 Jul 2019 17:40:49 +0000. Up 18.84 seconds."
        )
        infh.close()
        outfh = open(log_path, "w+")
        outfh.close()

    def set_up_dummy_file(self, path, log_path):
        infh = open(path, "w+")
        infh.write("dummy data")
        infh.close()
        outfh = open(log_path, "w+")
        outfh.close()

    def remove_dummy_file(self, path, log_path):
        if os.path.isfile(path):
            os.remove(path)
        if os.path.isfile(log_path):
            os.remove(log_path)

    @mock.patch(
        "cloudinit.analyze.show.dist_check_timestamp", return_value=err_code
    )
    def test_boot_invalid_distro(self, m_dist_check_timestamp):

        path = os.path.dirname(os.path.abspath(__file__))
        log_path = path + "/boot-test.log"
        path += "/dummy.log"
        self.set_up_dummy_file(path, log_path)

        parser = get_parser()
        args = parser.parse_args(args=["boot", "-i", path, "-o", log_path])
        name_default = ""
        analyze_boot(name_default, args)
        # now args have been tested, go into outfile and make sure error
        # message is in the outfile
        with open(args.outfile, "r") as outfh:
            data = outfh.read()
            err_string = (
                "Your Linux distro or container does not support this "
                "functionality.\nYou must be running a Kernel "
                "Telemetry supported distro.\nPlease check "
                "https://docs.cloud-init.io/en/latest/topics"
                "/analyze.html for more information on supported "
                "distros.\n"
            )

            self.remove_dummy_file(path, log_path)
            assert err_string == data

    @mock.patch("cloudinit.util.is_container", return_value=True)
    @mock.patch("cloudinit.subp.subp", return_value=("U=1000000", None))
    def test_container_no_ci_log_line(self, m_is_container, m_subp):
        path = os.path.dirname(os.path.abspath(__file__))
        log_path = path + "/boot-test.log"
        path += "/dummy.log"
        self.set_up_dummy_file(path, log_path)

        parser = get_parser()
        args = parser.parse_args(args=["boot", "-i", path, "-o", log_path])
        name_default = ""

        finish_code = analyze_boot(name_default, args)

        self.remove_dummy_file(path, log_path)
        assert FAIL_CODE == finish_code

    @mock.patch("cloudinit.util.is_container", return_value=True)
    @mock.patch("cloudinit.subp.subp", return_value=("U=1000000", None))
    @mock.patch(
        "cloudinit.analyze._get_events",
        return_value=[
            {
                "name": "init-local",
                "description": "starting search",
                "timestamp": 100000,
            }
        ],
    )
    @mock.patch(
        "cloudinit.analyze.show.dist_check_timestamp",
        return_value=(CONTAINER_CODE, 1, 1, 1),
    )
    def test_container_ci_log_line(self, m_is_container, m_subp, m_get, m_g):
        path = os.path.dirname(os.path.abspath(__file__))
        log_path = path + "/boot-test.log"
        path += "/dummy.log"
        self.set_up_dummy_file_ci(path, log_path)

        parser = get_parser()
        args = parser.parse_args(args=["boot", "-i", path, "-o", log_path])
        name_default = ""
        finish_code = analyze_boot(name_default, args)

        self.remove_dummy_file(path, log_path)
        assert CONTAINER_CODE == finish_code

    @mock.patch("time.time", return_value=100)
    @mock.patch("cloudinit.util.uptime", return_value=96)
    @mock.patch("time.monotonic", return_value=97)
    @mock.patch("cloudinit.analyze.show.SystemctlReader")
    @pytest.mark.parametrize(
        (
            "is_container_returnvalue",
            "time_mock_expected_callcount",
            "monotonic_mock_expected_callcount",
            "expected_return",
        ),
        (
            (True, 2, 1, (CONTAINER_CODE, 4, 33, 43)),
            (False, 1, 0, (SUCCESS_CODE, 4, 34, 44)),
        ),
    )
    def test_gather_timestamps_using_systemd(
        self,
        mock_SystemctlReader,
        monotonic_mock,
        uptime_mock,
        time_mock,
        is_container_returnvalue,
        time_mock_expected_callcount,
        monotonic_mock_expected_callcount,
        expected_return,
        mocker,
    ):
        """
        Testing the behavior based on whether or not the
        instance is a container
        """
        mocker.patch(
            "cloudinit.util.is_container",
            return_value=is_container_returnvalue,
        )
        systemctlReader_mocks = [
            mock.Mock(name="UserspaceTimestampMonotonic"),
            mock.Mock(name="InactiveExitTimestampMonotonic"),
        ]
        systemctlReader_mocks[0].parse_epoch_as_float.return_value = 30
        systemctlReader_mocks[1].parse_epoch_as_float.return_value = 40
        mock_SystemctlReader.side_effect = systemctlReader_mocks
        assert gather_timestamps_using_systemd() == expected_return

        assert time_mock.call_count == time_mock_expected_callcount
        assert uptime_mock.call_count == 1
        assert monotonic_mock.call_count == monotonic_mock_expected_callcount

    @mock.patch(
        "cloudinit.analyze.show.SystemctlReader",
        side_effect=Exception("ARandomError"),
    )
    def test_gather_timestamps_using_systemd_with_SystemctlReader_exception(
        self, systemctlReader_mock
    ):
        """
        Confirm the function returns the error code when SystemctlReader
        raises an exception
        """
        assert gather_timestamps_using_systemd() == err_code
