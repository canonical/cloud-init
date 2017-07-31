# This file is part of cloud-init. See LICENSE file for license information.

from ..helpers import (CiTestCase, mock)

from cloudinit.distros.debian import apply_locale
from cloudinit import util


@mock.patch("cloudinit.distros.debian.util.subp")
class TestDebianApplyLocale(CiTestCase):
    def test_no_rerun(self, m_subp):
        """If system has defined locale, no re-run is expected."""
        spath = self.tmp_path("default-locale")
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(spath, 'LANG=%s\n' % locale, omode="w")
        apply_locale(locale, sys_path=spath)
        m_subp.assert_not_called()

    def test_rerun_if_different(self, m_subp):
        """If system has different locale, locale-gen should be called."""
        spath = self.tmp_path("default-locale")
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        util.write_file(spath, 'LANG=fr_FR.UTF-8', omode="w")
        apply_locale(locale, sys_path=spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + spath, 'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_if_no_file(self, m_subp):
        """If system has no locale file, locale-gen should be called."""
        spath = self.tmp_path("default-locale")
        m_subp.return_value = (None, None)
        locale = 'en_US.UTF-8'
        apply_locale(locale, sys_path=spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + spath, 'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_on_unset_system_locale(self, m_subp):
        """If system has unset locale, locale-gen should be called."""
        m_subp.return_value = (None, None)
        spath = self.tmp_path("default-locale")
        locale = 'en_US.UTF-8'
        util.write_file(spath, 'LANG=', omode="w")
        apply_locale(locale, sys_path=spath)
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + spath, 'LANG=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_rerun_on_mismatched_keys(self, m_subp):
        """If key is LC_ALL and system has only LANG, rerun is expected."""
        m_subp.return_value = (None, None)
        spath = self.tmp_path("default-locale")
        locale = 'en_US.UTF-8'
        util.write_file(spath, 'LANG=', omode="w")
        apply_locale(locale, sys_path=spath, keyname='LC_ALL')
        self.assertEqual(
            [['locale-gen', locale],
             ['update-locale', '--locale-file=' + spath,
              'LC_ALL=%s' % locale]],
            [p[0][0] for p in m_subp.call_args_list])

    def test_falseish_locale_raises_valueerror(self, m_subp):
        """locale as None or "" is invalid and should raise ValueError."""

        with self.assertRaises(ValueError) as ctext_m:
            apply_locale(None)
            m_subp.assert_not_called()

        self.assertEqual(
            'Failed to provide locale value.', str(ctext_m.exception))

        with self.assertRaises(ValueError) as ctext_m:
            apply_locale("")
            m_subp.assert_not_called()
        self.assertEqual(
            'Failed to provide locale value.', str(ctext_m.exception))
