# This file is part of cloud-init. See LICENSE file for license information.

import glob
import os
import pathlib
import sys
import tarfile
from datetime import datetime, timezone

import pytest

from cloudinit.cmd.devel import logs
from cloudinit.cmd.devel.logs import ApportFile
from cloudinit.subp import SubpResult, subp
from cloudinit.util import ensure_dir, load_text_file, write_file

M_PATH = "cloudinit.cmd.devel.logs."
INSTANCE_JSON_SENSITIVE_FILE = "instance-data-sensitive.json"


def fake_subp(cmd):
    if cmd[0] == "tar" and cmd[1] == "czf":
        subp(cmd)  # Pass through tar cmd so we can check output
        return SubpResult("", "")

    expected_subp = {
        (
            "dpkg-query",
            "--show",
            "-f=${Version}\n",
            "cloud-init",
        ): "0.7fake\n",
        ("cloud-init", "--version"): "over 9000\n",
    }
    cmd_tuple = tuple(cmd)
    if cmd_tuple not in expected_subp:
        raise AssertionError(
            "Unexpected command provided to subp: {0}".format(cmd)
        )

    return SubpResult(expected_subp[cmd_tuple], "")


# the new _stream_command_output_to_file function uses subprocess.call
# instead of subp, so we need to mock that as well
def fake_subprocess_call(cmd, stdout=None, stderr=None):
    expected_calls = {
        ("dmesg",): "dmesg-out\n",
        ("journalctl", "--boot=0", "-o", "short-precise"): "journal-out\n",
        ("journalctl", "--boot=-1", "-o", "short-precise"): "journal-prev\n",
    }
    cmd_tuple = tuple(cmd)
    if cmd_tuple not in expected_calls:
        raise AssertionError(
            "Unexpected command provided to subprocess: {0}".format(cmd)
        )
    stdout.write(expected_calls[cmd_tuple])


def patch_subiquity_paths(mocker, tmp_path):
    mocker.patch(
        "cloudinit.cmd.devel.logs.INSTALLER_APPORT_FILES",
        [
            ApportFile(
                str(tmp_path / "subiquity-server-debug.log"),
                "subiquityServerDebug",
            )
        ],
    )
    mocker.patch(
        "cloudinit.cmd.devel.logs.INSTALLER_APPORT_SENSITIVE_FILES",
        [
            ApportFile(
                str(tmp_path / "autoinstall-user-data"), "AutoInstallUserData"
            )
        ],
    )


class TestCollectLogs:
    def test_collect_logs_requires_root_user(self, mocker):
        """collect-logs errors when non-root user collects userdata ."""
        # 100 is non-root
        mocker.patch("cloudinit.cmd.devel.logs.os.getuid", retrn_value=100)
        # If we don't mock this, we can change logging for future tests
        mocker.patch("cloudinit.cmd.devel.logs._setup_logger")
        with pytest.raises(
            RuntimeError, match="This command must be run as root"
        ):
            logs.collect_logs_cli("")

    def test_collect_logs_end_to_end(self, mocker, tmp_path):
        mocker.patch(f"{M_PATH}subp", side_effect=fake_subp)
        mocker.patch(
            f"{M_PATH}subprocess.call", side_effect=fake_subprocess_call
        )
        mocker.patch(
            f"{M_PATH}_get_etc_cloud",
            return_value=[
                tmp_path / "etc/cloud/cloud.cfg",
                tmp_path / "etc/cloud/cloud.cfg.d/90-dpkg.cfg",
            ],
        )
        patch_subiquity_paths(mocker, tmp_path)
        today = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

        # This list isn't exhaustive
        to_collect = [
            "etc/cloud/cloud.cfg",
            "etc/cloud/cloud.cfg.d/90-dpkg.cfg",
            "var/lib/cloud/instance/instance-id",
            "var/lib/cloud/instance/user-data.txt",
            "var/lib/cloud/instance/user-data.txt.i",
            "var/lib/cloud/handlers/wtf-i-wrote-a-handler.py",
            "var/log/cloud-init.log",
            "var/log/cloud-init-output.log",
            "var/log/cloud-init.log.1.gz",
            "var/log/cloud-init-output.log.1.gz",
            "run/cloud-init/results.json",
            "run/cloud-init/status.json",
            "run/cloud-init/instance-data-sensitive.json",
            "run/cloud-init/instance-data.json",
            "subiquity-server-debug.log",
            "autoinstall-user-data",
        ]
        for to_write in to_collect:
            write_file(tmp_path / to_write, pathlib.Path(to_write).name)

        # logs.collect_logs("cloud-init.tar.gz", {})
        logs.collect_logs(
            tarfile=tmp_path / "cloud-init.tar.gz",
            log_cfg={
                "def_log_file": str(tmp_path / "var/log/cloud-init.log"),
                "output": {
                    "all": f"| tee -a {tmp_path}/var/log/cloud-init-output.log"
                },
            },
            run_dir=tmp_path / "run/cloud-init",
            cloud_dir=tmp_path / "var/lib/cloud",
            include_sensitive=True,
        )
        extract_to = tmp_path / "extracted"
        extract_to.mkdir()

        tar_kwargs = {}
        if sys.version_info > (3, 11):
            tar_kwargs = {"filter": "fully_trusted"}
        with tarfile.open(tmp_path / "cloud-init.tar.gz") as tar:
            tar.extractall(extract_to, **tar_kwargs)  # type: ignore[arg-type]
        extracted_dir = extract_to / f"cloud-init-logs-{today}"

        for name in to_collect:
            # Since we've collected absolute paths, that means even though
            # our extract contents are within the tmp_path, the files will
            # include another layer of tmp_path directories
            assert (extracted_dir / str(tmp_path)[1:] / name).exists()

        assert (extracted_dir / "journal.txt").read_text() == "journal-out\n"
        assert (extracted_dir / "dmesg.txt").read_text() == "dmesg-out\n"
        assert (extracted_dir / "dpkg-version").read_text() == "0.7fake\n"
        assert (extracted_dir / "version").read_text() == "over 9000\n"

    def test_logs_and_installer_ignore_sensitive_flag(self, mocker, tmp_path):
        """Regardless of the sensitive flag, we always want these logs."""
        mocker.patch(f"{M_PATH}subp", side_effect=fake_subp)
        mocker.patch(
            f"{M_PATH}subprocess.call", side_effect=fake_subprocess_call
        )
        mocker.patch(f"{M_PATH}_get_etc_cloud", return_value=[])
        patch_subiquity_paths(mocker, tmp_path)

        to_collect = [
            "var/log/cloud-init.log",
            "var/log/cloud-init-output.log",
            "var/log/cloud-init.log.1.gz",
            "var/log/cloud-init-output.log.1.gz",
            "subiquity-server-debug.log",
        ]

        for to_write in to_collect:
            write_file(
                tmp_path / to_write, pathlib.Path(to_write).name, mode=0x700
            )

        collect_dir = tmp_path / "collect"
        collect_dir.mkdir()
        logs._collect_logs_into_tmp_dir(
            log_dir=collect_dir,
            log_cfg={
                "def_log_file": str(tmp_path / "var/log/cloud-init.log"),
                "output": {
                    "all": f"| tee -a {tmp_path}/var/log/cloud-init-output.log"
                },
            },
            run_dir=collect_dir,
            cloud_dir=collect_dir,
            include_sensitive=False,
        )

        for name in to_collect:
            assert (collect_dir / str(tmp_path)[1:] / name).exists()

    def test_root_read_only_not_collected_on_redact(self, mocker, tmp_path):
        """Don't collect root read-only files."""
        mocker.patch(f"{M_PATH}subp", side_effect=fake_subp)
        mocker.patch(
            f"{M_PATH}subprocess.call", side_effect=fake_subprocess_call
        )
        mocker.patch(f"{M_PATH}_get_etc_cloud", return_value=[])
        patch_subiquity_paths(mocker, tmp_path)

        to_collect = [
            "etc/cloud/cloud.cfg",
            "etc/cloud/cloud.cfg.d/90-dpkg.cfg",
            "var/lib/cloud/instance/instance-id",
            "var/lib/cloud/instance/user-data.txt",
            "var/lib/cloud/instance/user-data.txt.i",
            "var/lib/cloud/handlers/wtf-i-wrote-a-handler.py",
            "run/cloud-init/results.json",
            "run/cloud-init/status.json",
            "run/cloud-init/instance-data-sensitive.json",
            "run/cloud-init/instance-data.json",
            "autoinstall-user-data",
        ]

        for to_write in to_collect:
            write_file(
                tmp_path / to_write, pathlib.Path(to_write).name, mode=0x700
            )

        collect_dir = tmp_path / "collect"
        collect_dir.mkdir()
        logs._collect_logs_into_tmp_dir(
            log_dir=collect_dir,
            log_cfg={
                "def_log_file": str(tmp_path / "var/log/cloud-init.log"),
                "output": {
                    "all": f"| tee -a {tmp_path}/var/log/cloud-init-output.log"
                },
            },
            run_dir=collect_dir,
            cloud_dir=collect_dir,
            include_sensitive=False,
        )

        for name in to_collect:
            assert not (collect_dir / str(tmp_path)[1:] / name).exists()
        assert not (collect_dir / "dmsg.txt").exists()

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
        tmp_path,
        cmd,
        expected_file_contents,
        expected_return_value,
    ):
        output_file = tmp_path / "test-output-file.txt"

        return_output = logs._write_command_output_to_file(
            cmd=cmd,
            file_path=output_file,
            msg="",
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
        self, tmp_path, cmd, expected_file_contents
    ):
        output_file = tmp_path / "test-output-file.txt"

        logs._stream_command_output_to_file(
            cmd=cmd,
            file_path=output_file,
            msg="",
        )

        assert expected_file_contents == load_text_file(output_file)


class TestCollectInstallerLogs:
    @pytest.mark.parametrize(
        "include_sensitive, apport_files, apport_sensitive_files",
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
        include_sensitive,
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
            if include_sensitive:
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
            include_sensitive=include_sensitive,
        )
        expect_userdata = bool(include_sensitive and apport_sensitive_files)
        # when subiquity artifacts exist, and userdata set true, expect logs
        expect_subiquity_logs = any([apport_files, expect_userdata])
        if expect_subiquity_logs:
            assert destination_dir.exists(), "Missing subiquity artifact dir"
            assert sorted(expected_files) == sorted(
                glob.glob(f"{destination_dir.strpath}/*")
            )
        else:
            assert not destination_dir.exists(), "Unexpected subiquity dir"
