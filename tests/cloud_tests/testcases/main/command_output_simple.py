# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests.testcases import base


class TestCommandOutputSimple(base.CloudTestCase):
    """
    test functionality of simple output redirection
    """

    def test_output_file(self):
        """
        ensure that the output file is not empty and has all stages
        """
        data = self.get_data_file('cloud-init-test-output')
        self.assertNotEqual(len(data), 0, "specified log empty")
        self.assertEqual(self.get_config_entry('final_message'),
                         data.splitlines()[-1].strip())
        # TODO: need to test that all stages redirected here

# vi: ts=4 expandtab
