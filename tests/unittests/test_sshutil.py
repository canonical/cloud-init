# This file is part of cloud-init. See LICENSE file for license information.

from mock import patch

from cloudinit import ssh_util
from cloudinit.tests import helpers as test_helpers
from cloudinit import util


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
    'ecdsa-sha2-nistp256': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMy/WuXq5MF"
        "r5hVQ9EEKKUTF7vUaOkgxUh6bNsCs9SFMVslIm1zM/WJYwUv52LdEePjtDYiV4A"
        "l2XthJ9/bs7Pc="
    ),
    'ecdsa-sha2-nistp521': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHA1MjEAAAAIbmlzdHA1MjEAAACFBABOdNTkh9F"
        "McK4hZRLs5LTXBEXwNr0+Yg9uvJYRFcz2ZlnjYX9tM4Z3QQFjqogU4pU+zpKLqZ"
        "5VE4Jcnb1T608UywBIdXkSFZT8trGJqBv9nFWGgmTX3KP8kiBbihpuv1cGwglPl"
        "Hxs50A42iP0JiT7auGtEAGsu/uMql323GTGb4171Q=="
    ),
    'ecdsa-sha2-nistp384': (
        "AAAAE2VjZHNhLXNoYTItbmlzdHAzODQAAAAIbmlzdHAzODQAAABhBAnoqFU9Gnl"
        "LcsEuCJnobs/c6whzvjCgouaOO61kgXNtIxyF4Wkutg6xaGYgBBt/phb7a2TurI"
        "bcIBuzJ/mP22UyUAbNnBfStAEBmYbrTf1EfiMCYUAr1XnL0UdYmZ8HFg=="
    ),
}

TEST_OPTIONS = (
    "no-port-forwarding,no-agent-forwarding,no-X11-forwarding,"
    'command="echo \'Please login as the user \"ubuntu\" rather than the'
    'user \"root\".\';echo;sleep 10"')


class TestAuthKeyLineParser(test_helpers.CiTestCase):

    def test_simple_parse(self):
        # test key line with common 3 fields (keytype, base64, comment)
        parser = ssh_util.AuthKeyLineParser()
        ecdsa_types = [
            'ecdsa-sha2-nistp256',
            'ecdsa-sha2-nistp384',
            'ecdsa-sha2-nistp521',
        ]

        for ktype in ['rsa', 'ecdsa', 'dsa'] + ecdsa_types:
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


class TestUpdateAuthorizedKeys(test_helpers.CiTestCase):

    def test_new_keys_replace(self):
        """new entries with the same base64 should replace old."""
        orig_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'orig_comment1')),
            ' '.join(('dsa', VALID_CONTENT['dsa'], 'orig_comment2'))]

        new_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'new_comment1')), ]

        expected = '\n'.join([new_entries[0], orig_entries[1]]) + '\n'

        parser = ssh_util.AuthKeyLineParser()
        found = ssh_util.update_authorized_keys(
            [parser.parse(p) for p in orig_entries],
            [parser.parse(p) for p in new_entries])

        self.assertEqual(expected, found)

    def test_new_invalid_keys_are_ignored(self):
        """new entries that are invalid should be skipped."""
        orig_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'orig_comment1')),
            ' '.join(('dsa', VALID_CONTENT['dsa'], 'orig_comment2'))]

        new_entries = [
            ' '.join(('rsa', VALID_CONTENT['rsa'], 'new_comment1')),
            'xxx-invalid-thing1',
            'xxx-invalid-blob2'
        ]

        expected = '\n'.join([new_entries[0], orig_entries[1]]) + '\n'

        parser = ssh_util.AuthKeyLineParser()
        found = ssh_util.update_authorized_keys(
            [parser.parse(p) for p in orig_entries],
            [parser.parse(p) for p in new_entries])

        self.assertEqual(expected, found)


class TestParseSSHConfig(test_helpers.CiTestCase):

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


class TestUpdateSshConfigLines(test_helpers.CiTestCase):
    """Test the update_ssh_config_lines method."""
    exlines = [
        "#PasswordAuthentication yes",
        "UsePAM yes",
        "# Comment line",
        "AcceptEnv LANG LC_*",
        "X11Forwarding no",
    ]
    pwauth = "PasswordAuthentication"

    def check_line(self, line, opt, val):
        self.assertEqual(line.key, opt.lower())
        self.assertEqual(line.value, val)
        self.assertIn(opt, str(line))
        self.assertIn(val, str(line))

    def test_new_option_added(self):
        """A single update of non-existing option."""
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {'MyKey': 'MyVal'})
        self.assertEqual(['MyKey'], result)
        self.check_line(lines[-1], "MyKey", "MyVal")

    def test_commented_out_not_updated_but_appended(self):
        """Implementation does not un-comment and update lines."""
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {self.pwauth: "no"})
        self.assertEqual([self.pwauth], result)
        self.check_line(lines[-1], self.pwauth, "no")

    def test_single_option_updated(self):
        """A single update should have change made and line updated."""
        opt, val = ("UsePAM", "no")
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, {opt: val})
        self.assertEqual([opt], result)
        self.check_line(lines[1], opt, val)

    def test_multiple_updates_with_add(self):
        """Verify multiple updates some added some changed, some not."""
        updates = {"UsePAM": "no", "X11Forwarding": "no", "NewOpt": "newval",
                   "AcceptEnv": "LANG ADD LC_*"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual(set(["UsePAM", "NewOpt", "AcceptEnv"]), set(result))
        self.check_line(lines[3], "AcceptEnv", updates["AcceptEnv"])

    def test_return_empty_if_no_changes(self):
        """If there are no changes, then return should be empty list."""
        updates = {"UsePAM": "yes"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual([], result)
        self.assertEqual(self.exlines, [str(l) for l in lines])

    def test_keycase_not_modified(self):
        """Original case of key should not be changed on update.
        This behavior is to keep original config as much intact as can be."""
        updates = {"usepam": "no"}
        lines = ssh_util.parse_ssh_config_lines(list(self.exlines))
        result = ssh_util.update_ssh_config_lines(lines, updates)
        self.assertEqual(["usepam"], result)
        self.assertEqual("UsePAM no", str(lines[1]))


class TestUpdateSshConfig(test_helpers.CiTestCase):
    cfgdata = '\n'.join(["#Option val", "MyKey ORIG_VAL", ""])

    def test_modified(self):
        mycfg = self.tmp_path("ssh_config_1")
        util.write_file(mycfg, self.cfgdata)
        ret = ssh_util.update_ssh_config({"MyKey": "NEW_VAL"}, mycfg)
        self.assertTrue(ret)
        found = util.load_file(mycfg)
        self.assertEqual(self.cfgdata.replace("ORIG_VAL", "NEW_VAL"), found)
        # assert there is a newline at end of file (LP: #1677205)
        self.assertEqual('\n', found[-1])

    def test_not_modified(self):
        mycfg = self.tmp_path("ssh_config_2")
        util.write_file(mycfg, self.cfgdata)
        with patch("cloudinit.ssh_util.util.write_file") as m_write_file:
            ret = ssh_util.update_ssh_config({"MyKey": "ORIG_VAL"}, mycfg)
        self.assertFalse(ret)
        self.assertEqual(self.cfgdata, util.load_file(mycfg))
        m_write_file.assert_not_called()


# vi: ts=4 expandtab
