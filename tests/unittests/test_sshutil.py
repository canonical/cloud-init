# This file is part of cloud-init. See LICENSE file for license information.

from mock import patch

from . import helpers as test_helpers
from cloudinit import ssh_util


VALID_CONTENT = {
    'dsa': (
        "AAAAB3NzaC1kc3MAAACBAIrjOQSlSea19bExXBMBKBvcLhBoVvNBjCppNzllipF"
        "W4jgIOMcNanULRrZGjkOKat6MWJNetSbV1E6IOFDQ16rQgsh/OvYU9XhzM8seLa"
        "A21VszZuhIV7/2DE3vxu7B54zVzueG1O1Deq6goQCRGWBUnqO2yluJiG4HzrnDa"
        "jzRAAAAFQDMPO96qXd4F5A+5b2f2MO7SpVomQAAAIBpC3K2zIbDLqBBs1fn7rsv"
        "KcJvwihdlVjG7UXsDB76P2GNqVG+IlYPpJZ8TO/B/fzTMtrdXp9pSm9OY1+BgN4"
        "REsZ2WNcvfgY33aWaEM+ieCcQigvxrNAF2FTVcbUIIxAn6SmHuQSWrLSfdHc8H7"
        "hsrgeUPPdzjBD/cv2ZmqwZ1AAAAIAplIsScrJut5wJMgyK1JG0Kbw9JYQpLe95P"
        "obB069g8+mYR8U0fysmTEdR44mMu0VNU5E5OhTYoTGfXrVrkR134LqFM2zpVVbE"
        "JNDnIqDHxTkc6LY2vu8Y2pQ3/bVnllZZOda2oD5HQ7ovygQa6CH+fbaZHbdDUX/"
        "5z7u2rVAlDw=="
    ),
    'ecdsa': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBITrGBB3cgJ"
        "J7fPxvtMW9H3oRisNpJ3OAslxZeyP7I0A9BPAW0RQIwHVtVnM7zrp4nI+JLZov/"
        "Ql7lc2leWL7CY="
    ),
    'rsa': (
        "AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZdQueUq5oz"
        "emNSj8T7enqKHOEaFoU2VoPgGEWC9RyzSQVeyD6s7APMcE82EtmW4skVEgEGSbD"
        "c1pvxzxtchBj78hJP6Cf5TCMFSXw+Fz5rF1dR23QDbN1mkHs7adr8GW4kSWqU7Q"
        "7NDwfIrJJtO7Hi42GyXtvEONHbiRPOe8stqUly7MvUoN+5kfjBM8Qqpfl2+FNhT"
        "YWpMfYdPUnE7u536WqzFmsaqJctz3gBxH9Ex7dFtrxR4qiqEr9Qtlu3xGn7Bw07"
        "/+i1D+ey3ONkZLN+LQ714cgj8fRS4Hj29SCmXp5Kt5/82cD/VN3NtHw=="
    ),
}

TEST_OPTIONS = (
    "no-port-forwarding,no-agent-forwarding,no-X11-forwarding,"
    'command="echo \'Please login as the user \"ubuntu\" rather than the'
    'user \"root\".\';echo;sleep 10"')


class TestAuthKeyLineParser(test_helpers.TestCase):
    def test_simple_parse(self):
        # test key line with common 3 fields (keytype, base64, comment)
        parser = ssh_util.AuthKeyLineParser()
        for ktype in ['rsa', 'ecdsa', 'dsa']:
            content = VALID_CONTENT[ktype]
            comment = 'user-%s@host' % ktype
            line = ' '.join((ktype, content, comment,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertFalse(key.options)
            self.assertEqual(key.comment, comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_no_comment(self):
        # test key line with key type and base64 only
        parser = ssh_util.AuthKeyLineParser()
        for ktype in ['rsa', 'ecdsa', 'dsa']:
            content = VALID_CONTENT[ktype]
            line = ' '.join((ktype, content,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertFalse(key.options)
            self.assertFalse(key.comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_with_keyoptions(self):
        # test key line with options in it
        parser = ssh_util.AuthKeyLineParser()
        options = TEST_OPTIONS
        for ktype in ['rsa', 'ecdsa', 'dsa']:
            content = VALID_CONTENT[ktype]
            comment = 'user-%s@host' % ktype
            line = ' '.join((options, ktype, content, comment,))
            key = parser.parse(line)

            self.assertEqual(key.base64, content)
            self.assertEqual(key.options, options)
            self.assertEqual(key.comment, comment)
            self.assertEqual(key.keytype, ktype)

    def test_parse_with_options_passed_in(self):
        # test key line with key type and base64 only
        parser = ssh_util.AuthKeyLineParser()

        baseline = ' '.join(("rsa", VALID_CONTENT['rsa'], "user@host"))
        myopts = "no-port-forwarding,no-agent-forwarding"

        key = parser.parse("allowedopt" + " " + baseline)
        self.assertEqual(key.options, "allowedopt")

        key = parser.parse("overridden_opt " + baseline, options=myopts)
        self.assertEqual(key.options, myopts)

    def test_parse_invalid_keytype(self):
        parser = ssh_util.AuthKeyLineParser()
        key = parser.parse(' '.join(["badkeytype", VALID_CONTENT['rsa']]))

        self.assertFalse(key.valid())


class TestParseSSHConfig(test_helpers.TestCase):

    def setUp(self):
        self.load_file_patch = patch('cloudinit.ssh_util.util.load_file')
        self.load_file = self.load_file_patch.start()
        self.isfile_patch = patch('cloudinit.ssh_util.os.path.isfile')
        self.isfile = self.isfile_patch.start()
        self.isfile.return_value = True

    def tearDown(self):
        self.load_file_patch.stop()
        self.isfile_patch.stop()

    def test_not_a_file(self):
        self.isfile.return_value = False
        self.load_file.side_effect = IOError
        ret = ssh_util.parse_ssh_config('not a real file')
        self.assertEqual([], ret)

    def test_empty_file(self):
        self.load_file.return_value = ''
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual([], ret)

    def test_comment_line(self):
        comment_line = '# This is a comment'
        self.load_file.return_value = comment_line
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual(comment_line, ret[0].line)

    def test_blank_lines(self):
        lines = ['', '\t', ' ']
        self.load_file.return_value = '\n'.join(lines)
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(len(lines), len(ret))
        for line in ret:
            self.assertEqual('', line.line)

    def test_lower_case_config(self):
        self.load_file.return_value = 'foo bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)

    def test_upper_case_config(self):
        self.load_file.return_value = 'Foo Bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('Bar', ret[0].value)

    def test_lower_case_with_equals(self):
        self.load_file.return_value = 'foo=bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)

    def test_upper_case_with_equals(self):
        self.load_file.return_value = 'Foo=bar'
        ret = ssh_util.parse_ssh_config('some real file')
        self.assertEqual(1, len(ret))
        self.assertEqual('foo', ret[0].key)
        self.assertEqual('bar', ret[0].value)

# vi: ts=4 expandtab
