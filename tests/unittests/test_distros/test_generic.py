# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit import util

from cloudinit.tests import helpers

import os
import shutil
import tempfile

try:
    from unittest import mock
except ImportError:
    import mock

unknown_arch_info = {
    'arches': ['default'],
    'failsafe': {'primary': 'http://fs-primary-default',
                 'security': 'http://fs-security-default'}
}

package_mirrors = [
    {'arches': ['i386', 'amd64'],
     'failsafe': {'primary': 'http://fs-primary-intel',
                  'security': 'http://fs-security-intel'},
     'search': {
         'primary': ['http://%(ec2_region)s.ec2/',
                     'http://%(availability_zone)s.clouds/'],
         'security': ['http://security-mirror1-intel',
                      'http://security-mirror2-intel']}},
    {'arches': ['armhf', 'armel'],
     'failsafe': {'primary': 'http://fs-primary-arm',
                  'security': 'http://fs-security-arm'}},
    unknown_arch_info
]

gpmi = distros._get_package_mirror_info
gapmi = distros._get_arch_package_mirror_info


class TestGenericDistro(helpers.FilesystemMockingTestCase):

    def return_first(self, mlist):
        if not mlist:
            return None
        return mlist[0]

    def return_second(self, mlist):
        if not mlist:
            return None
        return mlist[1]

    def return_none(self, _mlist):
        return None

    def return_last(self, mlist):
        if not mlist:
            return None
        return(mlist[-1])

    def setUp(self):
        super(TestGenericDistro, self).setUp()
        # Make a temp directoy for tests to use.
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _write_load_sudoers(self, _user, rules):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        os.makedirs(os.path.join(self.tmp, "etc"))
        os.makedirs(os.path.join(self.tmp, "etc", 'sudoers.d'))
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        d.write_sudo_rules("harlowja", rules)
        contents = util.load_file(d.ci_sudoers_fn)
        return contents

    def _count_in(self, lines_look_for, text_content):
        found_amount = 0
        for e in lines_look_for:
            for line in text_content.splitlines():
                line = line.strip()
                if line == e:
                    found_amount += 1
        return found_amount

    def test_sudoers_ensure_rules(self):
        rules = 'ALL=(ALL:ALL) ALL'
        contents = self._write_load_sudoers('harlowja', rules)
        expected = ['harlowja ALL=(ALL:ALL) ALL']
        self.assertEqual(len(expected), self._count_in(expected, contents))
        not_expected = [
            'harlowja A',
            'harlowja L',
            'harlowja L',
        ]
        self.assertEqual(0, self._count_in(not_expected, contents))

    def test_sudoers_ensure_rules_list(self):
        rules = [
            'ALL=(ALL:ALL) ALL',
            'B-ALL=(ALL:ALL) ALL',
            'C-ALL=(ALL:ALL) ALL',
        ]
        contents = self._write_load_sudoers('harlowja', rules)
        expected = [
            'harlowja ALL=(ALL:ALL) ALL',
            'harlowja B-ALL=(ALL:ALL) ALL',
            'harlowja C-ALL=(ALL:ALL) ALL',
        ]
        self.assertEqual(len(expected), self._count_in(expected, contents))
        not_expected = [
            'harlowja A',
            'harlowja L',
            'harlowja L',
        ]
        self.assertEqual(0, self._count_in(not_expected, contents))

    def test_sudoers_ensure_new(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        d.ensure_sudo_dir("/b")
        contents = util.load_file("/etc/sudoers")
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))

    def test_sudoers_ensure_append(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        util.write_file("/etc/sudoers", "josh, josh\n")
        d.ensure_sudo_dir("/b")
        contents = util.load_file("/etc/sudoers")
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))
        self.assertIn("josh", contents)
        self.assertEqual(2, contents.count("josh"))

    def test_arch_package_mirror_info_unknown(self):
        """for an unknown arch, we should get back that with arch 'default'."""
        arch_mirrors = gapmi(package_mirrors, arch="unknown")
        self.assertEqual(unknown_arch_info, arch_mirrors)

    def test_arch_package_mirror_info_known(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        self.assertEqual(package_mirrors[0], arch_mirrors)

    def test_get_package_mirror_info_az_ec2(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        data_source_mock = mock.Mock(availability_zone="us-east-1a")

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_first)
        self.assertEqual(results,
                         {'primary': 'http://us-east-1.ec2/',
                          'security': 'http://security-mirror1-intel'})

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_second)
        self.assertEqual(results,
                         {'primary': 'http://us-east-1a.clouds/',
                          'security': 'http://security-mirror2-intel'})

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_none)
        self.assertEqual(results, package_mirrors[0]['failsafe'])

    def test_get_package_mirror_info_az_non_ec2(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        data_source_mock = mock.Mock(availability_zone="nova.cloudvendor")

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_first)
        self.assertEqual(results,
                         {'primary': 'http://nova.cloudvendor.clouds/',
                          'security': 'http://security-mirror1-intel'})

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_last)
        self.assertEqual(results,
                         {'primary': 'http://nova.cloudvendor.clouds/',
                          'security': 'http://security-mirror2-intel'})

    def test_get_package_mirror_info_none(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        data_source_mock = mock.Mock(availability_zone=None)

        # because both search entries here replacement based on
        # availability-zone, the filter will be called with an empty list and
        # failsafe should be taken.
        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_first)
        self.assertEqual(results,
                         {'primary': 'http://fs-primary-intel',
                          'security': 'http://security-mirror1-intel'})

        results = gpmi(arch_mirrors, data_source=data_source_mock,
                       mirror_filter=self.return_last)
        self.assertEqual(results,
                         {'primary': 'http://fs-primary-intel',
                          'security': 'http://security-mirror2-intel'})

    def test_systemd_in_use(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        os.makedirs('/run/systemd/system')
        self.assertTrue(d.uses_systemd())

    def test_systemd_not_in_use(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        self.assertFalse(d.uses_systemd())

    def test_systemd_symlink(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        os.makedirs('/run/systemd')
        os.symlink('/', '/run/systemd/system')
        self.assertFalse(d.uses_systemd())

    @mock.patch('cloudinit.distros.debian.read_system_locale')
    def test_get_locale_ubuntu(self, m_locale):
        """Test ubuntu distro returns locale set to C.UTF-8"""
        m_locale.return_value = 'C.UTF-8'
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        locale = d.get_locale()
        self.assertEqual('C.UTF-8', locale)

    def test_get_locale_rhel(self):
        """Test rhel distro returns NotImplementedError exception"""
        cls = distros.fetch("rhel")
        d = cls("rhel", {}, None)
        with self.assertRaises(NotImplementedError):
            d.get_locale()


# vi: ts=4 expandtab
