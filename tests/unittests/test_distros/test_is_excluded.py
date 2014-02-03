from cloudinit.distros import gentoo
import unittest


class TestIsExcluded(unittest.TestCase):

    def setUp(self):
        self.distro = gentoo.Distro('gentoo', {}, None)
        self.distro.exclude_modules = ['test-module']

    def test_is_excluded_success(self):
        self.assertEqual(self.distro.is_excluded('test-module'), True)

    def test_is_excluded_fail(self):
        self.assertEqual(self.distro.is_excluded('missing'), None)
