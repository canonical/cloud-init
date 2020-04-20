# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.subp utility functions"""

from cloudinit import subp
from cloudinit.tests.helpers import CiTestCase


class TestPrependBaseCommands(CiTestCase):

    with_logs = True

    def test_prepend_base_command_errors_on_neither_string_nor_list(self):
        """Raise an error for each command which is not a string or list."""
        orig_commands = ['ls', 1, {'not': 'gonna work'}, ['basecmd', 'list']]
        with self.assertRaises(TypeError) as context_manager:
            subp.prepend_base_command(
                base_command='basecmd', commands=orig_commands)
        self.assertEqual(
            "Invalid basecmd config. These commands are not a string or"
            " list:\n1\n{'not': 'gonna work'}",
            str(context_manager.exception))

    def test_prepend_base_command_warns_on_non_base_string_commands(self):
        """Warn on each non-base for commands of type string."""
        orig_commands = [
            'ls', 'basecmd list', 'touch /blah', 'basecmd install x']
        fixed_commands = subp.prepend_base_command(
            base_command='basecmd', commands=orig_commands)
        self.assertEqual(
            'WARNING: Non-basecmd commands in basecmd config:\n'
            'ls\ntouch /blah\n',
            self.logs.getvalue())
        self.assertEqual(orig_commands, fixed_commands)

    def test_prepend_base_command_prepends_on_non_base_list_commands(self):
        """Prepend 'basecmd' for each non-basecmd command of type list."""
        orig_commands = [['ls'], ['basecmd', 'list'], ['basecmda', '/blah'],
                         ['basecmd', 'install', 'x']]
        expected = [['basecmd', 'ls'], ['basecmd', 'list'],
                    ['basecmd', 'basecmda', '/blah'],
                    ['basecmd', 'install', 'x']]
        fixed_commands = subp.prepend_base_command(
            base_command='basecmd', commands=orig_commands)
        self.assertEqual('', self.logs.getvalue())
        self.assertEqual(expected, fixed_commands)

    def test_prepend_base_command_removes_first_item_when_none(self):
        """Remove the first element of a non-basecmd when it is None."""
        orig_commands = [[None, 'ls'], ['basecmd', 'list'],
                         [None, 'touch', '/blah'],
                         ['basecmd', 'install', 'x']]
        expected = [['ls'], ['basecmd', 'list'],
                    ['touch', '/blah'],
                    ['basecmd', 'install', 'x']]
        fixed_commands = subp.prepend_base_command(
            base_command='basecmd', commands=orig_commands)
        self.assertEqual('', self.logs.getvalue())
        self.assertEqual(expected, fixed_commands)

# vi: ts=4 expandtab
