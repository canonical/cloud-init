# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloud-id command line utility."""

from collections import namedtuple
from io import StringIO

from cloudinit import util
from cloudinit.cmd import cloud_id
from tests.unittests.helpers import CiTestCase, mock

M_PATH = "cloudinit.cmd.cloud_id."


class TestCloudId(CiTestCase):

    args = namedtuple("cloudidargs", "instance_data json long")

    def setUp(self):
        super(TestCloudId, self).setUp()
        self.tmp = self.tmp_dir()
        self.instance_data = self.tmp_path("instance-data.json", dir=self.tmp)

    def test_cloud_id_arg_parser_defaults(self):
        """Validate the argument defaults when not provided by the end-user."""
        cmd = ["cloud-id"]
        with mock.patch("sys.argv", cmd):
            args = cloud_id.get_parser().parse_args()
        self.assertEqual(
            "/run/cloud-init/instance-data.json", args.instance_data
        )
        self.assertEqual(False, args.long)
        self.assertEqual(False, args.json)

    def test_cloud_id_arg_parse_overrides(self):
        """Override argument defaults by specifying values for each param."""
        util.write_file(self.instance_data, "{}")
        cmd = [
            "cloud-id",
            "--instance-data",
            self.instance_data,
            "--long",
            "--json",
        ]
        with mock.patch("sys.argv", cmd):
            args = cloud_id.get_parser().parse_args()
        self.assertEqual(self.instance_data, args.instance_data)
        self.assertEqual(True, args.long)
        self.assertEqual(True, args.json)

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_missing_instance_data_json(self, get_status_details):
        """Exit error when the provided instance-data.json does not exist."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        cmd = ["cloud-id", "--instance-data", self.instance_data]
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stderr", new_callable=StringIO) as m_stderr:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(1, context_manager.exception.code)
        self.assertIn(
            "Error:\nFile not found '%s'" % self.instance_data,
            m_stderr.getvalue(),
        )

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_non_json_instance_data(self, get_status_details):
        """Exit error when the provided instance-data.json is not json."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        cmd = ["cloud-id", "--instance-data", self.instance_data]
        util.write_file(self.instance_data, "{")
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stderr", new_callable=StringIO) as m_stderr:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(1, context_manager.exception.code)
        self.assertIn(
            "Error:\nFile '%s' is not valid json." % self.instance_data,
            m_stderr.getvalue(),
        )

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_from_cloud_name_in_instance_data(
        self, get_status_details
    ):
        """Report canonical cloud-id from cloud_name in instance-data."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        util.write_file(
            self.instance_data,
            '{"v1": {"cloud_name": "mycloud", "region": "somereg"}}',
        )
        cmd = ["cloud-id", "--instance-data", self.instance_data]
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(0, context_manager.exception.code)
        self.assertEqual("mycloud\n", m_stdout.getvalue())

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_long_name_from_instance_data(self, get_status_details):
        """Report long cloud-id format from cloud_name and region."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        util.write_file(
            self.instance_data,
            '{"v1": {"cloud_name": "mycloud", "region": "somereg"}}',
        )
        cmd = ["cloud-id", "--instance-data", self.instance_data, "--long"]
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(0, context_manager.exception.code)
        self.assertEqual("mycloud\tsomereg\n", m_stdout.getvalue())

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_lookup_from_instance_data_region(
        self, get_status_details
    ):
        """Report discovered canonical cloud_id when region lookup matches."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        util.write_file(
            self.instance_data,
            '{"v1": {"cloud_name": "aws", "region": "cn-north-1",'
            ' "platform": "ec2"}}',
        )
        cmd = ["cloud-id", "--instance-data", self.instance_data, "--long"]
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(0, context_manager.exception.code)
        self.assertEqual("aws-china\tcn-north-1\n", m_stdout.getvalue())

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_lookup_json_instance_data_adds_cloud_id_to_json(
        self, get_status_details
    ):
        """Report v1 instance-data content with cloud_id when --json set."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        util.write_file(
            self.instance_data,
            '{"v1": {"cloud_name": "unknown", "region": "dfw",'
            ' "platform": "openstack", "public_ssh_keys": []}}',
        )
        expected = util.json_dumps(
            {
                "cloud_id": "openstack",
                "cloud_name": "unknown",
                "platform": "openstack",
                "public_ssh_keys": [],
                "region": "dfw",
            }
        )
        cmd = ["cloud-id", "--instance-data", self.instance_data, "--json"]
        with mock.patch("sys.argv", cmd):
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                with self.assertRaises(SystemExit) as context_manager:
                    cloud_id.main()
        self.assertEqual(0, context_manager.exception.code)
        self.assertEqual(expected + "\n", m_stdout.getvalue())


# vi: ts=4 expandtab
