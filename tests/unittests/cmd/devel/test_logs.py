# This file is part of cloud-init. See LICENSE file for license information.

import os
import re
from datetime import datetime
from io import StringIO

from cloudinit.cmd.devel import logs
from cloudinit.sources import INSTANCE_JSON_SENSITIVE_FILE
from cloudinit.subp import subp
from cloudinit.util import load_file, write_file
from tests.unittests.helpers import mock

M_PATH = "cloudinit.cmd.devel.logs."


@mock.patch("cloudinit.cmd.devel.logs.os.getuid")
class TestCollectLogs:
    def test_collect_logs_with_userdata_requires_root_user(
        self, m_getuid, tmpdir
    ):
        """collect-logs errors when non-root user collects userdata ."""
        m_getuid.return_value = 100  # non-root
        output_tarfile = tmpdir.join("logs.tgz")
        with mock.patch("sys.stderr", new_callable=StringIO) as m_stderr:
            assert 1 == logs.collect_logs(
                output_tarfile, include_userdata=True
            )
        assert (
            "To include userdata, root user is required."
            " Try sudo cloud-init collect-logs\n" == m_stderr.getvalue()
        )

    def test_collect_logs_creates_tarfile(self, m_getuid, mocker, tmpdir):
        """collect-logs creates a tarfile with all related cloud-init info."""
        m_getuid.return_value = 100
        log1 = tmpdir.join("cloud-init.log")
        write_file(log1, "cloud-init-log")
        log2 = tmpdir.join("cloud-init-output.log")
        write_file(log2, "cloud-init-output-log")
        run_dir = tmpdir.join("run")
        write_file(run_dir.join("results.json"), "results")
        write_file(
            run_dir.join(
                INSTANCE_JSON_SENSITIVE_FILE,
            ),
            "sensitive",
        )
        output_tarfile = str(tmpdir.join("logs.tgz"))

        date = datetime.utcnow().date().strftime("%Y-%m-%d")
        date_logdir = "cloud-init-logs-{0}".format(date)

        version_out = "/usr/bin/cloud-init 18.2fake\n"
        expected_subp = {
            (
                "dpkg-query",
                "--show",
                "-f=${Version}\n",
                "cloud-init",
            ): "0.7fake\n",
            ("cloud-init", "--version"): version_out,
            ("dmesg",): "dmesg-out\n",
            ("journalctl", "--boot=0", "-o", "short-precise"): "journal-out\n",
            ("tar", "czvf", output_tarfile, date_logdir): "",
        }

        def fake_subp(cmd):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    "Unexpected command provided to subp: {0}".format(cmd)
                )
            if cmd == ["tar", "czvf", output_tarfile, date_logdir]:
                subp(cmd)  # Pass through tar cmd so we can check output
            return expected_subp[cmd_tuple], ""

        fake_stderr = mock.MagicMock()

        mocker.patch(M_PATH + "subp", side_effect=fake_subp)
        mocker.patch(M_PATH + "sys.stderr", fake_stderr)
        mocker.patch(M_PATH + "CLOUDINIT_LOGS", [log1, log2])
        mocker.patch(M_PATH + "CLOUDINIT_RUN_DIR", run_dir)
        logs.collect_logs(output_tarfile, include_userdata=False)
        # unpack the tarfile and check file contents
        subp(["tar", "zxvf", output_tarfile, "-C", str(tmpdir)])
        out_logdir = tmpdir.join(date_logdir)
        assert not os.path.exists(
            os.path.join(
                out_logdir,
                "run",
                "cloud-init",
                INSTANCE_JSON_SENSITIVE_FILE,
            )
        ), (
            "Unexpected file found: %s" % INSTANCE_JSON_SENSITIVE_FILE
        )
        assert "0.7fake\n" == load_file(
            os.path.join(out_logdir, "dpkg-version")
        )
        assert version_out == load_file(os.path.join(out_logdir, "version"))
        assert "cloud-init-log" == load_file(
            os.path.join(out_logdir, "cloud-init.log")
        )
        assert "cloud-init-output-log" == load_file(
            os.path.join(out_logdir, "cloud-init-output.log")
        )
        assert "dmesg-out\n" == load_file(
            os.path.join(out_logdir, "dmesg.txt")
        )
        assert "journal-out\n" == load_file(
            os.path.join(out_logdir, "journal.txt")
        )
        assert "results" == load_file(
            os.path.join(out_logdir, "run", "cloud-init", "results.json")
        )
        fake_stderr.write.assert_any_call("Wrote %s\n" % output_tarfile)

    def test_collect_logs_includes_optional_userdata(
        self, m_getuid, mocker, tmpdir
    ):
        """collect-logs include userdata when --include-userdata is set."""
        m_getuid.return_value = 0
        log1 = tmpdir.join("cloud-init.log")
        write_file(log1, "cloud-init-log")
        log2 = tmpdir.join("cloud-init-output.log")
        write_file(log2, "cloud-init-output-log")
        userdata = tmpdir.join("user-data.txt")
        write_file(userdata, "user-data")
        run_dir = tmpdir.join("run")
        write_file(run_dir.join("results.json"), "results")
        write_file(
            run_dir.join(INSTANCE_JSON_SENSITIVE_FILE),
            "sensitive",
        )
        output_tarfile = str(tmpdir.join("logs.tgz"))

        date = datetime.utcnow().date().strftime("%Y-%m-%d")
        date_logdir = "cloud-init-logs-{0}".format(date)

        version_out = "/usr/bin/cloud-init 18.2fake\n"
        expected_subp = {
            (
                "dpkg-query",
                "--show",
                "-f=${Version}\n",
                "cloud-init",
            ): "0.7fake",
            ("cloud-init", "--version"): version_out,
            ("dmesg",): "dmesg-out\n",
            ("journalctl", "--boot=0", "-o", "short-precise"): "journal-out\n",
            ("tar", "czvf", output_tarfile, date_logdir): "",
        }

        def fake_subp(cmd):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    "Unexpected command provided to subp: {0}".format(cmd)
                )
            if cmd == ["tar", "czvf", output_tarfile, date_logdir]:
                subp(cmd)  # Pass through tar cmd so we can check output
            return expected_subp[cmd_tuple], ""

        fake_stderr = mock.MagicMock()

        mocker.patch(M_PATH + "subp", side_effect=fake_subp)
        mocker.patch(M_PATH + "sys.stderr", fake_stderr)
        mocker.patch(M_PATH + "CLOUDINIT_LOGS", [log1, log2])
        mocker.patch(M_PATH + "CLOUDINIT_RUN_DIR", run_dir)
        mocker.patch(M_PATH + "_get_user_data_file", return_value=userdata)
        logs.collect_logs(output_tarfile, include_userdata=True)
        # unpack the tarfile and check file contents
        subp(["tar", "zxvf", output_tarfile, "-C", str(tmpdir)])
        out_logdir = tmpdir.join(date_logdir)
        assert "user-data" == load_file(
            os.path.join(out_logdir, "user-data.txt")
        )
        assert "sensitive" == load_file(
            os.path.join(
                out_logdir,
                "run",
                "cloud-init",
                INSTANCE_JSON_SENSITIVE_FILE,
            )
        )
        fake_stderr.write.assert_any_call("Wrote %s\n" % output_tarfile)


class TestParser:
    def test_parser_help_has_userdata_file(self, mocker, tmpdir):
        userdata = str(tmpdir.join("user-data.txt"))
        mocker.patch(M_PATH + "_get_user_data_file", return_value=userdata)
        assert userdata in re.sub(r"\s+", "", logs.get_parser().format_help())
