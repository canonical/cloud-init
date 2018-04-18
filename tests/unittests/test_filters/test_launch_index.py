# This file is part of cloud-init. See LICENSE file for license information.

import copy

from cloudinit.tests import helpers

from six.moves import filterfalse

from cloudinit.filters import launch_index
from cloudinit import user_data as ud
from cloudinit import util


def count_messages(root):
    am = 0
    for m in root.walk():
        if ud.is_skippable(m):
            continue
        am += 1
    return am


class TestLaunchFilter(helpers.ResourceUsingTestCase):

    def assertCounts(self, message, expected_counts):
        orig_message = copy.deepcopy(message)
        for (index, count) in expected_counts.items():
            index = util.safe_int(index)
            filtered_message = launch_index.Filter(index).apply(message)
            self.assertEqual(count_messages(filtered_message), count)
        # Ensure original message still ok/not modified
        self.assertTrue(self.equivalentMessage(message, orig_message))

    def equivalentMessage(self, msg1, msg2):
        msg1_count = count_messages(msg1)
        msg2_count = count_messages(msg2)
        if msg1_count != msg2_count:
            return False
        # Do some basic payload checking
        msg1_msgs = [m for m in msg1.walk()]
        msg1_msgs = [m for m in filterfalse(ud.is_skippable, msg1_msgs)]
        msg2_msgs = [m for m in msg2.walk()]
        msg2_msgs = [m for m in filterfalse(ud.is_skippable, msg2_msgs)]
        for i in range(0, len(msg2_msgs)):
            m1_msg = msg1_msgs[i]
            m2_msg = msg2_msgs[i]
            if m1_msg.get_charset() != m2_msg.get_charset():
                return False
            if m1_msg.is_multipart() != m2_msg.is_multipart():
                return False
            m1_py = m1_msg.get_payload(decode=True)
            m2_py = m2_msg.get_payload(decode=True)
            if m1_py != m2_py:
                return False
        return True

    def testMultiEmailIndex(self):
        test_data = helpers.readResource('filter_cloud_multipart_2.email')
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(test_data)
        self.assertTrue(count_messages(message) > 0)
        # This file should have the following
        # indexes -> amount mapping in it
        expected_counts = {
            3: 1,
            2: 2,
            None: 3,
            -1: 0,
        }
        self.assertCounts(message, expected_counts)

    def testHeaderEmailIndex(self):
        test_data = helpers.readResource('filter_cloud_multipart_header.email')
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(test_data)
        self.assertTrue(count_messages(message) > 0)
        # This file should have the following
        # indexes -> amount mapping in it
        expected_counts = {
            5: 1,
            -1: 0,
            'c': 1,
            None: 1,
        }
        self.assertCounts(message, expected_counts)

    def testConfigEmailIndex(self):
        test_data = helpers.readResource('filter_cloud_multipart_1.email')
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(test_data)
        self.assertTrue(count_messages(message) > 0)
        # This file should have the following
        # indexes -> amount mapping in it
        expected_counts = {
            2: 1,
            -1: 0,
            None: 1,
        }
        self.assertCounts(message, expected_counts)

    def testNoneIndex(self):
        test_data = helpers.readResource('filter_cloud_multipart.yaml')
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(test_data)
        start_count = count_messages(message)
        self.assertTrue(start_count > 0)
        filtered_message = launch_index.Filter(None).apply(message)
        self.assertTrue(self.equivalentMessage(message, filtered_message))

    def testIndexes(self):
        test_data = helpers.readResource('filter_cloud_multipart.yaml')
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(test_data)
        start_count = count_messages(message)
        self.assertTrue(start_count > 0)
        # This file should have the following
        # indexes -> amount mapping in it
        expected_counts = {
            2: 2,
            3: 2,
            1: 2,
            0: 1,
            4: 1,
            7: 0,
            -1: 0,
            100: 0,
            # None should just give all back
            None: start_count,
            # Non ints should be ignored
            'c': start_count,
            # Strings should be converted
            '1': 2,
        }
        self.assertCounts(message, expected_counts)

# vi: ts=4 expandtab
