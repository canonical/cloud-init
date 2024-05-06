# This file is part of cloud-init. See LICENSE file for license information.

import glob
import os
import re
from datetime import datetime
from io import StringIO

import pytest

from cloudinit.cmd.devel import logs
from cloudinit.cmd.devel.logs import ApportFile
from cloudinit.subp import SubpResult, subp
from cloudinit.util import ensure_dir, load_text_file, write_file
from tests.unittests.helpers import mock

M_PATH = "cloudinit.cmd.devel.logs."
INSTANCE_JSON_SENSITIVE_FILE = "instance-data-sensitive.json"


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

    def test_collect_logs_creates_tarfile(
        self, m_getuid, m_log_paths, mocker, tmpdir
    ):
        """collect-logs creates a tarfile with all related cloud-init info."""
        m_getuid.return_value = 100
        log1 = tmpdir.join("cloud-init.log")
        write_file(log1, "cloud-init-log")
        log1_rotated = tmpdir.join("cloud-init.log.1.gz")
        write_file(log1_rotated, "cloud-init-log-rotated")
        log2 = tmpdir.join("cloud-init-output.log")
        write_file(log2, "cloud-init-output-log")
        log2_rotated = tmpdir.join("cloud-init-output.log.1.gz")
        write_file(log2_rotated, "cloud-init-output-log-rotated")
        run_dir = m_log_paths.run_dir
        write_file(str(run_dir / "results.json"), "results")
        write_file(
            str(m_log_paths.instance_data_sensitive),
            "sensitive",
        )
        output_tarfile = str(tmpdir.join("logs.tgz"))

        mocker.patch(M_PATH + "Init", autospec=True)
        mocker.patch(
            M_PATH + "get_config_logfiles",
            return_value=[log1, log1_rotated, log2, log2_rotated],
        )

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
            return SubpResult(expected_subp[cmd_tuple], "")

        # the new _stream_command_output_to_file function uses subprocess.call
        # instead of subp, so we need to mock that as well
        def fake_subprocess_call(cmd, stdout=None, stderr=None):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    "Unexpected command provided to subprocess: {0}".format(
                        cmd
                    )
                )
            stdout.write(expected_subp[cmd_tuple])

        fake_stderr = mock.MagicMock()

        mocker.patch(M_PATH + "subp", side_effect=fake_subp)
        mocker.patch(
            M_PATH + "subprocess.call", side_effect=fake_subprocess_call
        )
        mocker.patch(M_PATH + "sys.stderr", fake_stderr)
        mocker.patch(M_PATH + "INSTALLER_APPORT_FILES", [])
        mocker.patch(M_PATH + "INSTALLER_APPORT_SENSITIVE_FILES", [])
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
        assert "0.7fake\n" == load_text_file(
            os.path.join(out_logdir, "dpkg-version")
        )
        assert version_out == load_text_file(
            os.path.join(out_logdir, "version")
        )
        assert "cloud-init-log" == load_text_file(
            os.path.join(out_logdir, "cloud-init.log")
        )
        assert "cloud-init-log-rotated" == load_text_file(
            os.path.join(out_logdir, "cloud-init.log.1.gz")
        )
        assert "cloud-init-output-log" == load_text_file(
            os.path.join(out_logdir, "cloud-init-output.log")
        )
        assert "cloud-init-output-log-rotated" == load_text_file(
            os.path.join(out_logdir, "cloud-init-output.log.1.gz")
        )
        assert "dmesg-out\n" == load_text_file(
            os.path.join(out_logdir, "dmesg.txt")
        )
        assert "journal-out\n" == load_text_file(
            os.path.join(out_logdir, "journal.txt")
        )
        assert "results" == load_text_file(
            os.path.join(out_logdir, "run", "cloud-init", "results.json")
        )
        fake_stderr.write.assert_any_call("Wrote %s\n" % output_tarfile)

    def test_collect_logs_includes_optional_userdata(
        self, m_getuid, mocker, tmpdir, m_log_paths
    ):
        """collect-logs include userdata when --include-userdata is set."""
        m_getuid.return_value = 0
        log1 = tmpdir.join("cloud-init.log")
        write_file(log1, "cloud-init-log")
        log2 = tmpdir.join("cloud-init-output.log")
        write_file(log2, "cloud-init-output-log")
        userdata = m_log_paths.userdata_raw
        write_file(str(userdata), "user-data")
        run_dir = m_log_paths.run_dir
        write_file(str(run_dir / "results.json"), "results")
        write_file(
            str(m_log_paths.instance_data_sensitive),
            "sensitive",
        )
        output_tarfile = str(tmpdir.join("logs.tgz"))

        mocker.patch(M_PATH + "Init", autospec=True)
        mocker.patch(
            M_PATH + "get_config_logfiles",
            return_value=[log1, log2],
        )

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
            return SubpResult(expected_subp[cmd_tuple], "")

        def fake_subprocess_call(cmd, stdout=None, stderr=None):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    "Unexpected command provided to subprocess: {0}".format(
                        cmd
                    )
                )
            stdout.write(expected_subp[cmd_tuple])

        fake_stderr = mock.MagicMock()

        mocker.patch(M_PATH + "subp", side_effect=fake_subp)
        mocker.patch(
            M_PATH + "subprocess.call", side_effect=fake_subprocess_call
        )
        mocker.patch(M_PATH + "sys.stderr", fake_stderr)
        mocker.patch(M_PATH + "INSTALLER_APPORT_FILES", [])
        mocker.patch(M_PATH + "INSTALLER_APPORT_SENSITIVE_FILES", [])
        logs.collect_logs(output_tarfile, include_userdata=True)
        # unpack the tarfile and check file contents
        subp(["tar", "zxvf", output_tarfile, "-C", str(tmpdir)])
        out_logdir = tmpdir.join(date_logdir)
        assert "user-data" == load_text_file(
            os.path.join(out_logdir, userdata.name)
        )
        assert "sensitive" == load_text_file(
            os.path.join(
                out_logdir,
                "run",
                "cloud-init",
                m_log_paths.instance_data_sensitive.name,
            )
        )
        fake_stderr.write.assert_any_call("Wrote %s\n" % output_tarfile)

    @pytest.mark.parametrize(
        "cmd, expected_file_contents, expected_return_value",
        [
            (
                ["echo", "cloud-init? more like cloud-innit!"],
                "cloud-init? more like cloud-innit!\n",
                "cloud-init? more like cloud-innit!\n",
            ),
            (
                ["sh", "-c", "echo test 1>&2; exit 42"],
                (
                    "Unexpected error while running command.\n"
                    "Command: ['sh', '-c', 'echo test 1>&2; exit 42']\n"
                    "Exit code: 42\n"
                    "Reason: -\n"
                    "Stdout: \n"
                    "Stderr: test"
                ),
                None,
            ),
        ],
    )
    def test_write_command_output_to_file(
        self,
        m_getuid,
        tmpdir,
        cmd,
        expected_file_contents,
        expected_return_value,
    ):
        m_getuid.return_value = 100
        output_file = tmpdir.join("test-output-file.txt")

        return_output = logs._write_command_output_to_file(
            filename=output_file,
            cmd=cmd,
            msg="",
            verbosity=1,
        )

        assert expected_return_value == return_output
        assert expected_file_contents == load_text_file(output_file)

    @pytest.mark.parametrize(
        "cmd, expected_file_contents",
        [
            (["echo", "cloud-init, shmoud-init"], "cloud-init, shmoud-init\n"),
            (["sh", "-c", "echo test 1>&2; exit 42"], "test\n"),
        ],
    )
    def test_stream_command_output_to_file(
        self, m_getuid, tmpdir, cmd, expected_file_contents
    ):
        m_getuid.return_value = 100
        output_file = tmpdir.join("test-output-file.txt")

        logs._stream_command_output_to_file(
            filename=output_file,
            cmd=cmd,
            msg="",
            verbosity=1,
        )

        assert expected_file_contents == load_text_file(output_file)


class TestCollectInstallerLogs:
    @pytest.mark.parametrize(
        "include_userdata, apport_files, apport_sensitive_files",
        (
            pytest.param(True, [], [], id="no_files_include_userdata"),
            pytest.param(False, [], [], id="no_files_exclude_userdata"),
            pytest.param(
                True,
                (ApportFile("log1", "Label1"), ApportFile("log2", "Label2")),
                (
                    ApportFile("private1", "LabelPrivate1"),
                    ApportFile("private2", "PrivateLabel2"),
                ),
                id="files_and_dirs_include_userdata",
            ),
            pytest.param(
                False,
                (ApportFile("log1", "Label1"), ApportFile("log2", "Label2")),
                (
                    ApportFile("private1", "LabelPrivate1"),
                    ApportFile("private2", "PrivateLabel2"),
                ),
                id="files_and_dirs_exclude_userdata",
            ),
        ),
    )
    def test_include_installer_logs_when_present(
        self,
        include_userdata,
        apport_files,
        apport_sensitive_files,
        tmpdir,
        mocker,
    ):
        src_dir = tmpdir.join("src")
        ensure_dir(src_dir.strpath)
        # collect-logs nests full directory path to file in the tarfile
        destination_dir = tmpdir.join(src_dir)

        # Create tmppath-based userdata_files, installer_logs, installer_dirs
        expected_files = []
        # Create last file in list to assert ignoring absent files
        apport_files = [
            logs.ApportFile(src_dir.join(apport.path).strpath, apport.label)
            for apport in apport_files
        ]
        if apport_files:
            write_file(apport_files[-1].path, apport_files[-1].label)
            expected_files += [
                destination_dir.join(
                    os.path.basename(apport_files[-1].path)
                ).strpath
            ]
        apport_sensitive_files = [
            logs.ApportFile(src_dir.join(apport.path).strpath, apport.label)
            for apport in apport_sensitive_files
        ]
        if apport_sensitive_files:
            write_file(
                apport_sensitive_files[-1].path,
                apport_sensitive_files[-1].label,
            )
            if include_userdata:
                expected_files += [
                    destination_dir.join(
                        os.path.basename(apport_sensitive_files[-1].path)
                    ).strpath
                ]
        mocker.patch(M_PATH + "INSTALLER_APPORT_FILES", apport_files)
        mocker.patch(
            M_PATH + "INSTALLER_APPORT_SENSITIVE_FILES", apport_sensitive_files
        )
        logs._collect_installer_logs(
            log_dir=tmpdir.strpath,
            include_userdata=include_userdata,
            verbosity=0,
        )
        expect_userdata = bool(include_userdata and apport_sensitive_files)
        # when subiquity artifacts exist, and userdata set true, expect logs
        expect_subiquity_logs = any([apport_files, expect_userdata])
        if expect_subiquity_logs:
            assert destination_dir.exists(), "Missing subiquity artifact dir"
            assert sorted(expected_files) == sorted(
                glob.glob(f"{destination_dir.strpath}/*")
            )
        else:
            assert not destination_dir.exists(), "Unexpected subiquity dir"


class TestParser:
    def test_parser_help_has_userdata_file(self, m_log_paths, mocker, tmpdir):
        # userdata = str(tmpdir.join("user-data.txt"))
        userdata = m_log_paths.userdata_raw
        assert str(userdata) in re.sub(
            r"\s+", "", logs.get_parser().format_help()
        )
