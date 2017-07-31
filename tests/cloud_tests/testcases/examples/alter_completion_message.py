# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestFinalMessage(base.CloudTestCase):
    """Test cloud init module `cc_final_message`."""

    subs_char = '$'

    def get_final_message_config(self):
        """Get config for final message."""
        self.assertIn('final_message', self.cloud_config)
        return self.cloud_config['final_message']

    def get_final_message(self):
        """Get final message from log."""
        out = self.get_data_file('cloud-init-output.log')
        lines = len(self.get_final_message_config().splitlines())
        return '\n'.join(out.splitlines()[-1 * lines:])

    def test_final_message_string(self):
        """Ensure final handles regular strings."""
        for actual, config in zip(
                self.get_final_message().splitlines(),
                self.get_final_message_config().splitlines()):
            if self.subs_char not in config:
                self.assertEqual(actual, config)

    def test_final_message_subs(self):
        """Test variable substitution in final message."""
        # TODO: add verification of other substitutions
        patterns = {'$datasource': self.get_datasource()}
        for key, expected in patterns.items():
            index = self.get_final_message_config().splitlines().index(key)
            actual = self.get_final_message().splitlines()[index]
            self.assertEqual(actual, expected)

# vi: ts=4 expandtab
