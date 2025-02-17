# This file is part of cloud-init. See LICENSE file for license information.

import copy
import getpass
import os
import textwrap
from collections import namedtuple
from unittest import mock

import pytest

from cloudinit import features, safeyaml, util
from cloudinit.cmd import main
from cloudinit.util import ensure_dir, load_text_file, write_file

MyArgs = namedtuple(
    "MyArgs", "debug files force local reporter subcommand skip_log_setup"
)


CLOUD_CONFIG_ARCHIVE = """\
#cloud-config-archive
- type: "text/cloud-boothook"
  content: |
    #!/bin/sh
    echo "this is from a boothook." > /var/tmp/boothook.txt
- type: "text/cloud-config"
  content: |
    bootcmd:
    - echo "this is from a cloud-config." > /var/tmp/bootcmd.txt
"""


EXTRA_CLOUD_CONFIG = """\
#cloud-config
write_files
- path: {tmpdir}/etc/blah.ini
  content: override
"""


class TestMain:
    @pytest.fixture(autouse=True)
    def common_mocks(self, mocker):
        mocker.patch("cloudinit.cmd.main.os.getppid", return_value=42)
        mocker.patch("cloudinit.cmd.main.close_stdin")
        mocker.patch(
            "cloudinit.cmd.main.netinfo.debug_info",
            return_value="my net debug info",
        )
        mocker.patch(
            "cloudinit.cmd.main.util.fixup_output",
            return_value=("outfmt", "errfmt"),
        )
        mocker.patch("cloudinit.cmd.main.util.get_cmdline", return_value="")
        mocker.patch("cloudinit.cmd.main.util.uptime", return_value="12345")
        os.environ["_CLOUD_INIT_SAVE_STDOUT"] = "true"
        yield
        os.environ.pop("_CLOUD_INIT_SAVE_STDOUT")

    @pytest.fixture
    def cloud_cfg(self, mocker, tmpdir, fake_filesystem):
        cloud_dir = os.path.join(tmpdir, "var/lib/cloud/")
        log_dir = os.path.join(tmpdir, "var/log/")
        ensure_dir(cloud_dir)
        ensure_dir(os.path.join(tmpdir, "etc/cloud"))
        ensure_dir(log_dir)
        cloud_cfg_file = os.path.join(tmpdir, "etc/cloud/cloud.cfg")

        cfg = {
            "datasource_list": ["None"],
            # "def_log_file": os.path.join(log_dir, "cloud-init.log"),
            "def_log_file": "",
            "runcmd": ["ls /etc"],  # test ALL_DISTROS
            "system_info": {
                "paths": {
                    "cloud_dir": cloud_dir,
                    "run_dir": str(tmpdir),
                }
            },
            "write_files": [
                {
                    "path": os.path.join(tmpdir, "etc/blah.ini"),
                    "content": "blah",
                    "permissions": 0o755,
                    "owner": getpass.getuser(),
                },
            ],
            "cloud_init_modules": ["write_files", "runcmd"],
        }
        write_file(cloud_cfg_file, safeyaml.dumps(cfg))
        yield copy.deepcopy(cfg), cloud_cfg_file

    @pytest.mark.parametrize(
        "provide_file_arg,expected_file_content",
        (
            pytest.param(False, "blah", id="write_files_from_base_config"),
            pytest.param(
                True,
                "override",
                id="write_files_from_supplemental_file_arg",
            ),
        ),
    )
    def test_main_init_run_net_runs_modules(
        self,
        provide_file_arg,
        expected_file_content,
        cloud_cfg,
        capsys,
        tmpdir,
    ):
        """Modules like write_files are run in 'net' mode."""
        if provide_file_arg:
            supplemental_config_file = tmpdir.join("custom.yaml")
            supplemental_config_file.write(
                EXTRA_CLOUD_CONFIG.format(tmpdir=tmpdir)
            )
            files = [open(supplemental_config_file)]
        else:
            files = None
        cmdargs = MyArgs(
            debug=False,
            files=files,
            force=False,
            local=False,
            reporter=None,
            subcommand="init",
            skip_log_setup=False,
        )
        _ds, msg = main.main_init("init", cmdargs)
        assert msg == []
        # Instancify is called
        instance_id_path = "var/lib/cloud/data/instance-id"
        assert "iid-datasource-none\n" == os.path.join(
            load_text_file(os.path.join(tmpdir, instance_id_path))
        )
        # modules are run (including write_files)
        assert "blah" == load_text_file(os.path.join(tmpdir, "etc/blah.ini"))
        expected_logs = [
            "network config is disabled by fallback",  # apply_network_config
            "my net debug info",  # netinfo.debug_info
            "PID [42] started cloud-init 'init'",
        ]
        stderr = capsys.readouterr().err
        for log in expected_logs:
            assert log in stderr

    def test_main_init_run_net_calls_set_hostname_when_metadata_present(
        self, cloud_cfg, mocker
    ):
        """When local-hostname metadata is present, call cc_set_hostname."""
        cfg, cloud_cfg_file = cloud_cfg
        cfg["datasource"] = {
            "None": {"metadata": {"local-hostname": "md-hostname"}}
        }
        write_file(cloud_cfg_file, safeyaml.dumps(cfg))
        cmdargs = MyArgs(
            debug=False,
            files=None,
            force=False,
            local=False,
            reporter=None,
            subcommand="init",
            skip_log_setup=False,
        )

        def set_hostname(name, cfg, cloud, args):
            assert "set_hostname" == name

        m_hostname = mocker.patch(
            "cloudinit.cmd.main.cc_set_hostname.handle",
            side_effect=set_hostname,
        )
        main.main_init("init", cmdargs)

        m_hostname.assert_called_once()

    @mock.patch("cloudinit.cmd.clean.get_parser")
    @mock.patch("cloudinit.cmd.clean.handle_clean_args")
    @mock.patch("cloudinit.log.loggers.configure_root_logger")
    def test_main_sys_argv(
        self,
        _m_configure_root_logger,
        _m_handle_clean_args,
        m_clean_get_parser,
    ):
        with mock.patch("sys.argv", ["cloudinit", "--debug", "clean"]):
            main.main()
        m_clean_get_parser.assert_called_once()

    @pytest.mark.parametrize(
        "ds,userdata,expected",
        [
            # If we have no datasource, wait regardless
            (None, None, True),
            (None, "#!/bin/bash\n  - echo hello", True),
            # Empty user data shouldn't wait
            (mock.Mock(), "", False),
            # Bootcmd always wait
            (mock.Mock(), "#cloud-config\nbootcmd:\n  - echo hello", True),
            # Bytes are valid too
            (mock.Mock(), b"#cloud-config\nbootcmd:\n  - echo hello", True),
            # write_files with source uri wait
            (
                mock.Mock(),
                textwrap.dedent(
                    """\
                    #cloud-config
                    write_files:
                    - source:
                        uri: http://example.com
                        headers:
                          Authorization: Basic stuff
                          User-Agent: me
                    """
                ),
                True,
            ),
            # write_files with source file don't wait
            (
                mock.Mock(),
                textwrap.dedent(
                    """\
                    #cloud-config
                    write_files:
                    - source:
                        uri: /tmp/hi
                        headers:
                          Authorization: Basic stuff
                          User-Agent: me
                    """
                ),
                False,
            ),
            # write_files without 'source' don't wait
            (
                mock.Mock(),
                textwrap.dedent(
                    """\
                    #cloud-config
                    write_files:
                    - content: hello
                      encoding: b64
                      owner: root:root
                      path: /etc/sysconfig/selinux
                      permissions: '0644'
                    """
                ),
                False,
            ),
            # random_seed with 'command' wait
            (
                mock.Mock(),
                "#cloud-config\nrandom_seed:\n  command: true",
                True,
            ),
            # random_seed without 'command' no wait
            (
                mock.Mock(),
                textwrap.dedent(
                    """\
                    #cloud-config
                    random_seed:
                      data: 4
                      encoding: raw
                      file: /dev/urandom
                    """
                ),
                False,
            ),
            # mounts always wait
            (
                mock.Mock(),
                "#cloud-config\nmounts:\n  - [ /dev/sdb, /mnt, ext4 ]",
                True,
            ),
            # Not parseable as yaml
            (mock.Mock(), "#cloud-config\nbootcmd:\necho hello", True),
            # Yaml that parses to list
            (mock.Mock(), CLOUD_CONFIG_ARCHIVE, True),
            # Non-cloud-config
            (mock.Mock(), "#!/bin/bash\n  - echo hello", True),
            # Something that after processing won't decode to utf-8
            (mock.Mock(), "RANDOM100", True),
            # Something small that  after processing won't decode to utf-8
            (mock.Mock(), "RANDOM5", True),
        ],
    )
    def test_should_wait_on_network(self, ds, userdata, expected):
        # pytest-xdist doesn't like randomness
        # https://github.com/pytest-dev/pytest-xdist/issues/432
        # So work around it with a super stupid hack
        if userdata == "RANDOM100":
            userdata = os.urandom(100)
        elif userdata == "RANDOM5":
            userdata = os.urandom(5)

        if ds:
            ds.get_userdata_raw = mock.Mock(return_value=userdata)
            ds.get_vendordata_raw = mock.Mock(return_value=None)
            ds.get_vendordata2_raw = mock.Mock(return_value=None)
        assert main._should_wait_on_network(ds)[0] is expected

        # Here we rotate our configs to ensure that any of userdata,
        # vendordata, or vendordata2 can be the one that causes us to wait.
        for _ in range(2):
            if ds:
                (
                    ds.get_userdata_raw,
                    ds.get_vendordata_raw,
                    ds.get_vendordata2_raw,
                ) = (
                    ds.get_vendordata_raw,
                    ds.get_vendordata2_raw,
                    ds.get_userdata_raw,
                )
            assert main._should_wait_on_network(ds)[0] is expected

    @pytest.mark.parametrize(
        "distro,should_wait,expected_add_wait",
        [
            ("ubuntu", True, True),
            ("ubuntu", False, False),
            ("debian", True, False),
            ("debian", False, False),
            ("centos", True, False),
            ("rhel", False, False),
            ("fedora", True, False),
            ("suse", False, False),
            ("gentoo", True, False),
            ("arch", False, False),
            ("alpine", False, False),
        ],
    )
    def test_distro_wait_for_network(
        self,
        distro,
        should_wait,
        expected_add_wait,
        cloud_cfg,
        mocker,
        fake_filesystem,
    ):
        mocker.patch("cloudinit.net.netplan.available", return_value=True)
        m_nm = mocker.patch(
            "cloudinit.net.network_manager.available", return_value=False
        )
        m_subp = mocker.patch("cloudinit.subp.subp", return_value=("", ""))
        if not should_wait:
            util.write_file(".skip-network", "")

        cfg, cloud_cfg_file = cloud_cfg
        cfg["system_info"]["distro"] = distro
        write_file(cloud_cfg_file, safeyaml.dumps(cfg))
        cmdargs = MyArgs(
            debug=False,
            files=None,
            force=False,
            local=False,
            reporter=None,
            subcommand="init",
            skip_log_setup=False,
        )
        main.main_init("init", cmdargs)
        if features.MANUAL_NETWORK_WAIT and expected_add_wait:
            m_nm.assert_called_once()
            m_subp.assert_called_with(
                ["systemctl", "start", "systemd-networkd-wait-online.service"]
            )
        else:
            m_nm.assert_not_called()
            m_subp.assert_not_called()


class TestShouldBringUpInterfaces:
    @pytest.mark.parametrize(
        "cfg_disable,args_local,expected",
        [
            (True, True, False),
            (True, False, False),
            (False, True, False),
            (False, False, True),
        ],
    )
    def test_should_bring_up_interfaces(
        self, cfg_disable, args_local, expected
    ):
        init = mock.Mock()
        init.cfg = {"disable_network_activation": cfg_disable}

        args = mock.Mock()
        args.local = args_local

        result = main._should_bring_up_interfaces(init, args)
        assert result == expected
