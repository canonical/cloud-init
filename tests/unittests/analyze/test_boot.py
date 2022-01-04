import os

from cloudinit.analyze.__main__ import analyze_boot, get_parser
from cloudinit.analyze.show import (
    CONTAINER_CODE,
    FAIL_CODE,
    SystemctlReader,
    dist_check_timestamp,
)
from tests.unittests.helpers import CiTestCase, mock

err_code = (FAIL_CODE, -1, -1, -1)


class TestDistroChecker(CiTestCase):
    def test_blank_distro(self):
        self.assertEqual(err_code, dist_check_timestamp())

    @mock.patch("cloudinit.util.is_FreeBSD", return_value=True)
    def test_freebsd_gentoo_cant_find(self, m_is_FreeBSD):
        self.assertEqual(err_code, dist_check_timestamp())

    @mock.patch("cloudinit.subp.subp", return_value=(0, 1))
    def test_subp_fails(self, m_subp):
        self.assertEqual(err_code, dist_check_timestamp())


class TestSystemCtlReader(CiTestCase):
    def test_systemctl_invalid_property(self):
        reader = SystemctlReader("dummyProperty")
        with self.assertRaises(RuntimeError):
            reader.parse_epoch_as_float()

    def test_systemctl_invalid_parameter(self):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        with self.assertRaises(RuntimeError):
            reader.parse_epoch_as_float()

    @mock.patch("cloudinit.subp.subp", return_value=("U=1000000", None))
    def test_systemctl_works_correctly_threshold(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        self.assertEqual(1.0, reader.parse_epoch_as_float())
        thresh = 1.0 - reader.parse_epoch_as_float()
        self.assertTrue(thresh < 1e-6)
        self.assertTrue(thresh > (-1 * 1e-6))

    @mock.patch("cloudinit.subp.subp", return_value=("U=0", None))
    def test_systemctl_succeed_zero(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        self.assertEqual(0.0, reader.parse_epoch_as_float())

    @mock.patch("cloudinit.subp.subp", return_value=("U=1", None))
    def test_systemctl_succeed_distinct(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        val1 = reader.parse_epoch_as_float()
        m_subp.return_value = ("U=2", None)
        reader2 = SystemctlReader("dummyProperty", "dummyParameter")
        val2 = reader2.parse_epoch_as_float()
        self.assertNotEqual(val1, val2)

    @mock.patch("cloudinit.subp.subp", return_value=("100", None))
    def test_systemctl_epoch_not_splittable(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        with self.assertRaises(IndexError):
            reader.parse_epoch_as_float()

    @mock.patch("cloudinit.subp.subp", return_value=("U=foobar", None))
    def test_systemctl_cannot_convert_epoch_to_float(self, m_subp):
        reader = SystemctlReader("dummyProperty", "dummyParameter")
        with self.assertRaises(ValueError):
            reader.parse_epoch_as_float()


class TestAnalyzeBoot(CiTestCase):
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
        outfh = open(args.outfile, "r")
        data = outfh.read()
        err_string = (
            "Your Linux distro or container does not support this "
            "functionality.\nYou must be running a Kernel "
            "Telemetry supported distro.\nPlease check "
            "https://cloudinit.readthedocs.io/en/latest/topics"
            "/analyze.html for more information on supported "
            "distros.\n"
        )

        self.remove_dummy_file(path, log_path)
        self.assertEqual(err_string, data)

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
        self.assertEqual(FAIL_CODE, finish_code)

    @mock.patch("cloudinit.util.is_container", return_value=True)
    @mock.patch("cloudinit.subp.subp", return_value=("U=1000000", None))
    @mock.patch(
        "cloudinit.analyze.__main__._get_events",
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
        self.assertEqual(CONTAINER_CODE, finish_code)
