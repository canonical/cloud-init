# This file is part of cloud-init. See LICENSE file for license information.
import logging

from configobj import ConfigObj

from cloudinit import util
from cloudinit.config import cc_landscape
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    mock,
    wrap_and_call,
)
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestLandscape(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestLandscape, self).setUp()
        self.new_root = self.tmp_dir()
        self.conf = self.tmp_path("client.conf", self.new_root)
        self.default_file = self.tmp_path("default_landscape", self.new_root)
        self.patchUtils(self.new_root)
        self.add_patch(
            "cloudinit.distros.ubuntu.Distro.install_packages",
            "m_install_packages",
        )

    def test_handler_skips_empty_landscape_cloudconfig(self):
        """Empty landscape cloud-config section does no work."""
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {}}
        cc_landscape.handle("notimportant", cfg, mycloud, LOG, None)
        self.assertFalse(mycloud.distro.install_packages.called)

    def test_handler_error_on_invalid_landscape_type(self):
        """Raise an error when landscape configuraiton option is invalid."""
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": "wrongtype"}
        with self.assertRaises(RuntimeError) as context_manager:
            cc_landscape.handle("notimportant", cfg, mycloud, LOG, None)
        self.assertIn(
            "'landscape' key existed in config, but not a dict",
            str(context_manager.exception),
        )

    @mock.patch("cloudinit.config.cc_landscape.subp")
    def test_handler_restarts_landscape_client(self, m_subp):
        """handler restarts lansdscape-client after install."""
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": {"client": {}}}
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {"LSC_CLIENT_CFG_FILE": {"new": self.conf}},
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            LOG,
            None,
        )
        self.assertEqual(
            [mock.call(["service", "landscape-client", "restart"])],
            m_subp.subp.call_args_list,
        )

    def test_handler_installs_client_and_creates_config_file(self):
        """Write landscape client.conf and install landscape-client."""
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": {"client": {}}}
        expected = {
            "client": {
                "log_level": "info",
                "url": "https://landscape.canonical.com/message-system",
                "ping_url": "http://landscape.canonical.com/ping",
                "data_path": "/var/lib/landscape/client",
            }
        }
        mycloud.distro = mock.MagicMock()
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {
                "LSC_CLIENT_CFG_FILE": {"new": self.conf},
                "LS_DEFAULT_FILE": {"new": self.default_file},
            },
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            LOG,
            None,
        )
        self.assertEqual(
            [mock.call("landscape-client")],
            mycloud.distro.install_packages.call_args,
        )
        self.assertEqual(expected, dict(ConfigObj(self.conf)))
        self.assertIn(
            "Wrote landscape config file to {0}".format(self.conf),
            self.logs.getvalue(),
        )
        default_content = util.load_file(self.default_file)
        self.assertEqual("RUN=1\n", default_content)

    def test_handler_writes_merged_client_config_file_with_defaults(self):
        """Merge and write options from LSC_CLIENT_CFG_FILE with defaults."""
        # Write existing sparse client.conf file
        util.write_file(self.conf, "[client]\ncomputer_title = My PC\n")
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": {"client": {}}}
        expected = {
            "client": {
                "log_level": "info",
                "url": "https://landscape.canonical.com/message-system",
                "ping_url": "http://landscape.canonical.com/ping",
                "data_path": "/var/lib/landscape/client",
                "computer_title": "My PC",
            }
        }
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {"LSC_CLIENT_CFG_FILE": {"new": self.conf}},
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            LOG,
            None,
        )
        self.assertEqual(expected, dict(ConfigObj(self.conf)))
        self.assertIn(
            "Wrote landscape config file to {0}".format(self.conf),
            self.logs.getvalue(),
        )

    def test_handler_writes_merged_provided_cloudconfig_with_defaults(self):
        """Merge and write options from cloud-config options with defaults."""
        # Write empty sparse client.conf file
        util.write_file(self.conf, "")
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": {"client": {"computer_title": "My PC"}}}
        expected = {
            "client": {
                "log_level": "info",
                "url": "https://landscape.canonical.com/message-system",
                "ping_url": "http://landscape.canonical.com/ping",
                "data_path": "/var/lib/landscape/client",
                "computer_title": "My PC",
            }
        }
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {"LSC_CLIENT_CFG_FILE": {"new": self.conf}},
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            LOG,
            None,
        )
        self.assertEqual(expected, dict(ConfigObj(self.conf)))
        self.assertIn(
            "Wrote landscape config file to {0}".format(self.conf),
            self.logs.getvalue(),
        )
