# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestCommandOutputSimple(base.CloudTestCase):
    """Test functionality of simple output redirection."""

    def test_output_file(self):
        """Ensure that the output file is not empty and has all stages."""
        data = self.get_data_file('cloud-init-test-output')
        self.assertNotEqual(len(data), 0, "specified log empty")
        self.assertEqual(self.get_config_entry('final_message'),
                         data.splitlines()[-1].strip())
        # TODO: need to test that all stages redirected here

    def test_no_warnings_in_log(self):
        """Warnings should not be found in the log.

        This class redirected stderr and stdout, so it expects to find
        a warning in cloud-init.log to that effect."""
        redirect_msg = 'Stdout, stderr changing to'
        warnings = [
            l for l in self.get_data_file('cloud-init.log').splitlines()
            if 'WARN' in l]
        self.assertEqual(
            [], [w for w in warnings if redirect_msg not in w],
            msg="'WARN' found inside cloud-init.log")
        self.assertEqual(
            1, len(warnings),
            msg="Did not find %s in cloud-init.log" % redirect_msg)

# vi: ts=4 expandtab
