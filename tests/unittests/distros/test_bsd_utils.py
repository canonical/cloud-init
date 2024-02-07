# This file is part of cloud-init. See LICENSE file for license information.

import cloudinit.distros.bsd_utils as bsd_utils
from tests.unittests.helpers import CiTestCase, ExitStack, mock

RC_FILE = """
if something; then
    do something here
fi
hostname={hostname}
"""


class TestBsdUtils(CiTestCase):
    def setUp(self):
        super().setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.load_file = patches.enter_context(
            mock.patch.object(bsd_utils.util, "load_text_file")
        )

        self.write_file = patches.enter_context(
            mock.patch.object(bsd_utils.util, "write_file")
        )

    def test_get_rc_config_value(self):
        self.load_file.return_value = "hostname=foo\n"
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "foo")
        self.load_file.assert_called_with("/etc/rc.conf")

        self.load_file.return_value = "hostname=foo"
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "foo")

        self.load_file.return_value = 'hostname="foo"'
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "foo")

        self.load_file.return_value = "hostname='foo'"
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "foo")

        self.load_file.return_value = "hostname='foo\""
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "'foo\"")

        self.load_file.return_value = ""
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), None)

        self.load_file.return_value = RC_FILE.format(hostname="foo")
        self.assertEqual(bsd_utils.get_rc_config_value("hostname"), "foo")

    def test_set_rc_config_value_unchanged(self):
        # bsd_utils.set_rc_config_value('hostname', 'foo')
        # self.write_file.assert_called_with('/etc/rc.conf', 'hostname=foo\n')

        self.load_file.return_value = RC_FILE.format(hostname="foo")
        self.write_file.assert_not_called()

    def test_set_rc_config_value(self):
        bsd_utils.set_rc_config_value("hostname", "foo")
        self.write_file.assert_called_with("/etc/rc.conf", "hostname=foo\n")

        self.load_file.return_value = RC_FILE.format(hostname="foo")
        bsd_utils.set_rc_config_value("hostname", "bar")
        self.write_file.assert_called_with(
            "/etc/rc.conf", RC_FILE.format(hostname="bar")
        )
