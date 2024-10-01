# This file is part of cloud-init. See LICENSE file for license information.

import copy
import getpass
import os
from collections import namedtuple
from unittest import mock

import pytest

from cloudinit import safeyaml
from cloudinit.cmd import main
from cloudinit.util import ensure_dir, load_text_file, write_file

MyArgs = namedtuple(
    "MyArgs", "debug files force local reporter subcommand skip_log_setup"
)


class TestMain:
    @pytest.fixture(autouse=True)
    def common_mocks(self, mocker):
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

    def test_main_init_run_net_runs_modules(self, cloud_cfg, capsys, tmpdir):
        """Modules like write_files are run in 'net' mode."""
        cmdargs = MyArgs(
            debug=False,
            files=None,
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
