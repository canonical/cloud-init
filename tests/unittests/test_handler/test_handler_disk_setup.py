from cloudinit.config import cc_disk_setup
from ..helpers import ExitStack, mock, TestCase


class TestIsDiskUsed(TestCase):

    def setUp(self):
        super(TestIsDiskUsed, self).setUp()
        self.patches = ExitStack()
        mod_name = 'cloudinit.config.cc_disk_setup'
        self.enumerate_disk = self.patches.enter_context(
            mock.patch('{0}.enumerate_disk'.format(mod_name)))
        self.check_fs = self.patches.enter_context(
            mock.patch('{0}.check_fs'.format(mod_name)))

    def test_multiple_child_nodes_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(2))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        self.assertTrue(cc_disk_setup.is_disk_used(mock.MagicMock()))

    def test_valid_filesystem_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (
            mock.MagicMock(), 'ext4', mock.MagicMock())
        self.assertTrue(cc_disk_setup.is_disk_used(mock.MagicMock()))

    def test_one_child_nodes_and_no_fs_returns_false(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        self.assertFalse(cc_disk_setup.is_disk_used(mock.MagicMock()))
