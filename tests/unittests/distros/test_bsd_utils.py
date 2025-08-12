# This file is part of cloud-init. See LICENSE file for license information.
import pytest

import cloudinit.distros.bsd_utils as bsd_utils
from tests.unittests.helpers import mock

RC_FILE = """
if something; then
    do something here
fi
hostname={hostname}
"""


@mock.patch("cloudinit.distros.bsd_utils.util.load_text_file")
class TestBsdUtils:
    @pytest.mark.parametrize(
        "content,expected",
        (
            ("hostname=foo\n", "foo"),
            ("hostname=foo", "foo"),
            ('hostname="foo"', "foo"),
            ("hostname='foo'", "foo"),
            ("hostname='foo\"", "'foo\""),
            ("", None),
            (RC_FILE.format(hostname="foo"), "foo"),
        ),
    )
    def test_get_rc_config_value(self, m_load_file, content, expected):
        m_load_file.return_value = content
        assert bsd_utils.get_rc_config_value("hostname") == expected
        m_load_file.assert_called_with("/etc/rc.conf")

    @mock.patch("cloudinit.distros.bsd_utils.util.write_file")
    def test_set_rc_config_value_unchanged(self, m_write_file, m_load_file):
        m_load_file.return_value = RC_FILE.format(hostname="foo")
        m_write_file.assert_not_called()

    @mock.patch("cloudinit.distros.bsd_utils.util.write_file")
    def test_set_rc_config_value(self, m_write_file, m_load_file):
        bsd_utils.set_rc_config_value("hostname", "foo")
        m_write_file.assert_called_with("/etc/rc.conf", "hostname=foo\n")

        m_load_file.return_value = RC_FILE.format(hostname="foo")
        bsd_utils.set_rc_config_value("hostname", "bar")
        m_write_file.assert_called_with(
            "/etc/rc.conf", RC_FILE.format(hostname="bar")
        )
