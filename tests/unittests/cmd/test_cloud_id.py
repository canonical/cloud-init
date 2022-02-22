# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloud-id command line utility."""

from collections import namedtuple

import pytest

from cloudinit import util
from cloudinit.cmd import cloud_id
from tests.unittests.helpers import mock

M_PATH = "cloudinit.cmd.cloud_id."


class TestCloudId:

    args = namedtuple("cloudidargs", "instance_data json long")

    def test_cloud_id_arg_parser_defaults(self):
        """Validate the argument defaults when not provided by the end-user."""
        cmd = ["cloud-id"]
        with mock.patch("sys.argv", cmd):
            args = cloud_id.get_parser().parse_args()
        assert "/run/cloud-init/instance-data.json" == args.instance_data
        assert False is args.long
        assert False is args.json

    def test_cloud_id_arg_parse_overrides(self, tmpdir):
        """Override argument defaults by specifying values for each param."""
        instance_data = tmpdir.join("instance-data.json")
        instance_data.write("{}")
        cmd = [
            "cloud-id",
            "--instance-data",
            instance_data.strpath,
            "--long",
            "--json",
        ]
        with mock.patch("sys.argv", cmd):
            args = cloud_id.get_parser().parse_args()
        assert instance_data.strpath == args.instance_data
        assert True is args.long
        assert True is args.json

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_missing_instance_data_json(
        self, get_status_details, tmpdir, capsys
    ):
        """Exit error when the provided instance-data.json does not exist."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        cmd = ["cloud-id", "--instance-data", instance_data.strpath]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        assert 1 == context_manager.value.code
        _out, err = capsys.readouterr()
        assert "Error:\nFile not found '%s'" % instance_data.strpath in err

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_non_json_instance_data(
        self, get_status_details, tmpdir, capsys
    ):
        """Exit error when the provided instance-data.json is not json."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        cmd = ["cloud-id", "--instance-data", instance_data.strpath]
        instance_data.write("{")
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        assert 1 == context_manager.value.code
        _out, err = capsys.readouterr()
        assert (
            "Error:\nFile '%s' is not valid json." % instance_data.strpath
            in err
        )

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_from_cloud_name_in_instance_data(
        self, get_status_details, tmpdir, capsys
    ):
        """Report canonical cloud-id from cloud_name in instance-data."""
        instance_data = tmpdir.join("instance-data.json")
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data.write(
            '{"v1": {"cloud_name": "mycloud", "region": "somereg"}}',
        )
        cmd = ["cloud-id", "--instance-data", instance_data.strpath]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        assert 0 == context_manager.value.code
        out, _err = capsys.readouterr()
        assert "mycloud\n" == out

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_long_name_from_instance_data(
        self, get_status_details, tmpdir, capsys
    ):
        """Report long cloud-id format from cloud_name and region."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        instance_data.write(
            '{"v1": {"cloud_name": "mycloud", "region": "somereg"}}',
        )
        cmd = ["cloud-id", "--instance-data", instance_data.strpath, "--long"]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        out, _err = capsys.readouterr()
        assert 0 == context_manager.value.code
        assert "mycloud\tsomereg\n" == out

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_lookup_from_instance_data_region(
        self, get_status_details, tmpdir, capsys
    ):
        """Report discovered canonical cloud_id when region lookup matches."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        instance_data.write(
            '{"v1": {"cloud_name": "aws", "region": "cn-north-1",'
            ' "platform": "ec2"}}',
        )
        cmd = ["cloud-id", "--instance-data", instance_data.strpath, "--long"]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        assert 0 == context_manager.value.code
        out, _err = capsys.readouterr()
        assert "aws-china\tcn-north-1\n" == out

    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_lookup_json_instance_data_adds_cloud_id_to_json(
        self, get_status_details, tmpdir, capsys
    ):
        """Report v1 instance-data content with cloud_id when --json set."""
        get_status_details.return_value = cloud_id.UXAppStatus.DONE, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        instance_data.write(
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
        cmd = ["cloud-id", "--instance-data", instance_data.strpath, "--json"]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        out, _err = capsys.readouterr()
        assert 0 == context_manager.value.code
        assert expected + "\n" == out

    @pytest.mark.parametrize(
        "status, exit_code",
        (
            (cloud_id.UXAppStatus.DISABLED, 2),
            (cloud_id.UXAppStatus.NOT_RUN, 3),
            (cloud_id.UXAppStatus.RUNNING, 0),
        ),
    )
    @mock.patch(M_PATH + "get_status_details")
    def test_cloud_id_unique_exit_codes_for_status(
        self, get_status_details, status, exit_code, tmpdir, capsys
    ):
        """cloud-id returns unique exit codes for status."""
        get_status_details.return_value = status, "n/a", ""
        instance_data = tmpdir.join("instance-data.json")
        if status == cloud_id.UXAppStatus.RUNNING:
            instance_data.write("{}")
        cmd = ["cloud-id", "--instance-data", instance_data.strpath, "--json"]
        with mock.patch("sys.argv", cmd):
            with pytest.raises(SystemExit) as context_manager:
                cloud_id.main()
        assert exit_code == context_manager.value.code


# vi: ts=4 expandtab
