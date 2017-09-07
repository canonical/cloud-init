# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit import util
from cloudinit.tests.helpers import (FilesystemMockingTestCase, mock)


@mock.patch("cloudinit.distros.debian.util.subp")
class TestDebianApplyLocale(FilesystemMockingTestCase):

    def setUp(self):
        super(TestDebianApplyLocale, self).setUp()
        self.new_root = self.tmp_dir()
        self.patchOS(self.new_root)
        self.patchUtils(self.new_root)
        self.spath = self.tmp_path('etc/default/locale', self.new_root)
        cls = distros.fetch("debian")
        self.distro = cls("debian", {}, None)

    def test_no_rerun(self, m_subp):
        """If system has defined locale, no re-run is expected."""
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(self.spath, 'LANG=%s\n' % locale, omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        m_subp.assert_not_called()

    def test_no_regen_on_c_utf8(self, m_subp):
        """If locale is set to C.UTF8, do not attempt to call locale-gen"""
        m_subp.return_value = (None, None)
        locale = 'C.UTF-8'
        util.write_file(self.spath, 'LANG=%s\n' % 'en_US.UTF-8', omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [['update-locale', '--locale-file=' + self.spath,
              'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_if_different(self, m_subp):
        """If system has different locale, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(self.spath, 'LANG=fr_FR.UTF-8', omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + self.spath,
              'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_if_no_file(self, m_subp):
        """If system has no locale file, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + self.spath,
              'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_on_unset_system_locale(self, m_subp):
        """If system has unset locale, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(self.spath, 'LANG=', omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + self.spath,
              'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_on_mismatched_keys(self, m_subp):
        """If key is LC_ALL and system has only LANG, rerun is expected."""
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(self.spath, 'LANG=', omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath, keyname='LC_ALL')
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + self.spath,
              'LC_ALL=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_falseish_locale_raises_valueerror(self, m_subp):
        """locale as None or "" is invalid and should raise ValueError."""

        with self.assertRaises(ValueError) as ctext_m:
            self.distro.apply_locale(None)
            m_subp.assert_not_called()

        self.assertEqual(
            'Failed to provide locale value.', str(ctext_m.exception))

        with self.assertRaises(ValueError) as ctext_m:
            self.distro.apply_locale("")
            m_subp.assert_not_called()
        self.assertEqual(
            'Failed to provide locale value.', str(ctext_m.exception))
