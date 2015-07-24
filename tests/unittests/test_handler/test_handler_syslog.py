from cloudinit.config.cc_syslog import (
    parse_remotes_line, SyslogRemotesLine, remotes_to_rsyslog_cfg)
from cloudinit import util
from .. import helpers as t_help


class TestParseRemotesLine(t_help.TestCase):
    def test_valid_port(self):
        r = parse_remotes_line("foo:9")
        self.assertEqual(9, r.port)

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            parse_remotes_line("*.* foo:abc")

    def test_valid_ipv6(self):
        r = parse_remotes_line("*.* [::1]")
        self.assertEqual("*.* [::1]", str(r))

    def test_valid_ipv6_with_port(self):
        r = parse_remotes_line("*.* [::1]:100")
        self.assertEqual(r.port, 100)
        self.assertEqual(r.addr, "::1")
        self.assertEqual("*.* [::1]:100", str(r))

    def test_invalid_multiple_colon(self):
        with self.assertRaises(ValueError):
            parse_remotes_line("*.* ::1:100")

    def test_name_in_string(self):
        r = parse_remotes_line("syslog.host", name="foobar")
        self.assertEqual("*.* syslog.host # foobar", str(r))
