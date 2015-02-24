from . import helpers

from six.moves import filterfalse

from cloudinit import user_data as ud
from cloudinit import util

def count_messages(root):
    am = 0
    for m in root.walk():
        if ud.is_skippable(m):
            continue
        am += 1
    return am


class TestUDProcess(helpers.ResourceUsingTestCase):

    def testBytesInPayload(self):
        msg = b'#cloud-config\napt_update: True\n'
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)

    def testStringInPayload(self):
        msg = '#cloud-config\napt_update: True\n'

        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)
