# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os
from collections import namedtuple
from io import StringIO
from unittest import mock

import pytest

from cloudinit import safeyaml
from cloudinit.cmd import main
from cloudinit.util import ensure_dir, load_text_file, write_file
from tests.unittests.helpers import FilesystemMockingTestCase, wrap_and_call

MyArgs = namedtuple("MyArgs", "debug files force local reporter subcommand")


class TestMain(FilesystemMockingTestCase):
    with_logs = True
    allowed_subp = False

    def setUp(self):
        super(TestMain, self).setUp()
        self.new_root = self.tmp_dir()
        self.cloud_dir = self.tmp_path("var/lib/cloud/", dir=self.new_root)
        os.makedirs(self.cloud_dir)
        self.replicateTestRoot("simple_ubuntu", self.new_root)
        self.cfg = {
            "datasource_list": ["None"],
            "runcmd": ["ls /etc"],  # test ALL_DISTROS
            "system_info": {
                "paths": {
                    "cloud_dir": self.cloud_dir,
                    "run_dir": self.new_root,
                }
            },
            "write_files": [
                {
                    "path": "/etc/blah.ini",
                    "content": "blah",
                    "permissions": 0o755,
                },
            ],
            "cloud_init_modules": ["write_files", "runcmd"],
        }
        cloud_cfg = safeyaml.dumps(self.cfg)
        ensure_dir(os.path.join(self.new_root, "etc", "cloud"))
        self.cloud_cfg_file = os.path.join(
            self.new_root, "etc", "cloud", "cloud.cfg"
        )
        write_file(self.cloud_cfg_file, cloud_cfg)
        self.patchOS(self.new_root)
        self.patchUtils(self.new_root)
        self.stderr = StringIO()
        self.patchStdoutAndStderr(stderr=self.stderr)
        # Every cc_ module calls get_meta_doc on import.
        # This call will fail if filesystem redirection mocks are in place
        # and the module hasn't already been imported which can depend
        # on test ordering.
        self.m_doc = mock.patch(
            "cloudinit.config.schema.get_meta_doc", return_value={}
        )
        self.m_doc.start()

    def tearDown(self):
        self.m_doc.stop()
        super().tearDown()

    def test_main_init_run_net_runs_modules(self):
        """Modules like write_files are run in 'net' mode."""
        cmdargs = MyArgs(
            debug=False,
            files=None,
            force=False,
            local=False,
            reporter=None,
            subcommand="init",
        )
        (_item1, item2) = wrap_and_call(
            "cloudinit.cmd.main",
            {
                "close_stdin": True,
                "netinfo.debug_info": "my net debug info",
                "util.fixup_output": ("outfmt", "errfmt"),
            },
            main.main_init,
            "init",
            cmdargs,
        )
        self.assertEqual([], item2)
        # Instancify is called
        instance_id_path = "var/lib/cloud/data/instance-id"
        self.assertEqual(
            "iid-datasource-none\n",
            os.path.join(
                load_text_file(os.path.join(self.new_root, instance_id_path))
            ),
        )
        # modules are run (including write_files)
        self.assertEqual(
            "blah", load_text_file(os.path.join(self.new_root, "etc/blah.ini"))
        )
        expected_logs = [
            "network config is disabled by fallback",  # apply_network_config
            "my net debug info",  # netinfo.debug_info
        ]
        for log in expected_logs:
            self.assertIn(log, self.stderr.getvalue())

    def test_main_init_run_net_calls_set_hostname_when_metadata_present(self):
        """When local-hostname metadata is present, call cc_set_hostname."""
        self.cfg["datasource"] = {
            "None": {"metadata": {"local-hostname": "md-hostname"}}
        }
        cloud_cfg = safeyaml.dumps(self.cfg)
        write_file(self.cloud_cfg_file, cloud_cfg)
        cmdargs = MyArgs(
            debug=False,
            files=None,
            force=False,
            local=False,
            reporter=None,
            subcommand="init",
        )

        def set_hostname(name, cfg, cloud, args):
            self.assertEqual("set_hostname", name)
            updated_cfg = copy.deepcopy(self.cfg)
            updated_cfg.update(
                {
                    "def_log_file": "/var/log/cloud-init.log",
                    "log_cfgs": [],
                    "syslog_fix_perms": [
                        "syslog:adm",
                        "root:adm",
                        "root:wheel",
                        "root:root",
                    ],
                    "vendor_data": {"enabled": True, "prefix": []},
                    "vendor_data2": {"enabled": True, "prefix": []},
                }
            )
            updated_cfg.pop("system_info")

            self.assertEqual(updated_cfg, cfg)
            self.assertIsNone(args)

        (_item1, item2) = wrap_and_call(
            "cloudinit.cmd.main",
            {
                "close_stdin": True,
                "netinfo.debug_info": "my net debug info",
                "cc_set_hostname.handle": {"side_effect": set_hostname},
                "util.fixup_output": ("outfmt", "errfmt"),
            },
            main.main_init,
            "init",
            cmdargs,
        )
        self.assertEqual([], item2)
        # Instancify is called
        instance_id_path = "var/lib/cloud/data/instance-id"
        self.assertEqual(
            "iid-datasource-none\n",
            os.path.join(
                load_text_file(os.path.join(self.new_root, instance_id_path))
            ),
        )
        # modules are run (including write_files)
        self.assertEqual(
            "blah", load_text_file(os.path.join(self.new_root, "etc/blah.ini"))
        )
        expected_logs = [
            "network config is disabled by fallback",  # apply_network_config
            "my net debug info",  # netinfo.debug_info
        ]
        for log in expected_logs:
            self.assertIn(log, self.stderr.getvalue())

    @mock.patch("cloudinit.cmd.clean.get_parser")
    @mock.patch("cloudinit.cmd.clean.handle_clean_args")
    @mock.patch("cloudinit.log.configure_root_logger")
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
