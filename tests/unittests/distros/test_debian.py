# This file is part of cloud-init. See LICENSE file for license information.
from itertools import count, cycle
from unittest import mock

import pytest

from cloudinit import distros, subp, util
from cloudinit.distros.debian import APT_GET_COMMAND, APT_GET_WRAPPER
from tests.unittests.helpers import FilesystemMockingTestCase


@mock.patch("cloudinit.distros.debian.subp.subp")
class TestDebianApplyLocale(FilesystemMockingTestCase):
    def setUp(self):
        super(TestDebianApplyLocale, self).setUp()
        self.new_root = self.tmp_dir()
        self.patchOS(self.new_root)
        self.patchUtils(self.new_root)
        self.spath = self.tmp_path("etc/default/locale", self.new_root)
        cls = distros.fetch("debian")
        self.distro = cls("debian", {}, None)

    def test_no_rerun(self, m_subp):
        """If system has defined locale, no re-run is expected."""
        m_subp.return_value = (None, None)
        locale = "en_US.UTF-8"
        util.write_file(self.spath, "LANG=%s\n" % locale, omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        m_subp.assert_not_called()

    def test_no_regen_on_c_utf8(self, m_subp):
        """If locale is set to C.UTF8, do not attempt to call locale-gen"""
        m_subp.return_value = (None, None)
        locale = "C.UTF-8"
        util.write_file(self.spath, "LANG=%s\n" % "en_US.UTF-8", omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [
                [
                    "update-locale",
                    "--locale-file=" + self.spath,
                    "LANG=%s" % locale,
                ]
            ],
            [p[0][0] for p in m_subp.call_args_list],
        )

    def test_rerun_if_different(self, m_subp):
        """If system has different locale, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = "en_US.UTF-8"
        util.write_file(self.spath, "LANG=fr_FR.UTF-8", omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [
                ["locale-gen", locale],
                [
                    "update-locale",
                    "--locale-file=" + self.spath,
                    "LANG=%s" % locale,
                ],
            ],
            [p[0][0] for p in m_subp.call_args_list],
        )

    def test_rerun_if_no_file(self, m_subp):
        """If system has no locale file, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = "en_US.UTF-8"
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [
                ["locale-gen", locale],
                [
                    "update-locale",
                    "--locale-file=" + self.spath,
                    "LANG=%s" % locale,
                ],
            ],
            [p[0][0] for p in m_subp.call_args_list],
        )

    def test_rerun_on_unset_system_locale(self, m_subp):
        """If system has unset locale, locale-gen should be called."""
        m_subp.return_value = (None, None)
        locale = "en_US.UTF-8"
        util.write_file(self.spath, "LANG=", omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath)
        self.assertEqual(
            [
                ["locale-gen", locale],
                [
                    "update-locale",
                    "--locale-file=" + self.spath,
                    "LANG=%s" % locale,
                ],
            ],
            [p[0][0] for p in m_subp.call_args_list],
        )

    def test_rerun_on_mismatched_keys(self, m_subp):
        """If key is LC_ALL and system has only LANG, rerun is expected."""
        m_subp.return_value = (None, None)
        locale = "en_US.UTF-8"
        util.write_file(self.spath, "LANG=", omode="w")
        self.distro.apply_locale(locale, out_fn=self.spath, keyname="LC_ALL")
        self.assertEqual(
            [
                ["locale-gen", locale],
                [
                    "update-locale",
                    "--locale-file=" + self.spath,
                    "LC_ALL=%s" % locale,
                ],
            ],
            [p[0][0] for p in m_subp.call_args_list],
        )

    def test_falseish_locale_raises_valueerror(self, m_subp):
        """locale as None or "" is invalid and should raise ValueError."""

        with self.assertRaises(ValueError) as ctext_m:
            self.distro.apply_locale(None)
            m_subp.assert_not_called()

        self.assertEqual(
            "Failed to provide locale value.", str(ctext_m.exception)
        )

        with self.assertRaises(ValueError) as ctext_m:
            self.distro.apply_locale("")
            m_subp.assert_not_called()
        self.assertEqual(
            "Failed to provide locale value.", str(ctext_m.exception)
        )


@mock.patch.dict("os.environ", {}, clear=True)
@mock.patch("cloudinit.distros.debian.subp.which", return_value=True)
@mock.patch("cloudinit.distros.debian.subp.subp")
class TestPackageCommand:
    distro = distros.fetch("debian")("debian", {}, None)

    @mock.patch(
        "cloudinit.distros.debian.Distro._apt_lock_available",
        return_value=True,
    )
    def test_simple_command(self, m_apt_avail, m_subp, m_which):
        self.distro.package_command("update")
        apt_args = [APT_GET_WRAPPER["command"]]
        apt_args.extend(APT_GET_COMMAND)
        apt_args.append("update")
        expected_call = {
            "args": apt_args,
            "capture": False,
            "env": {"DEBIAN_FRONTEND": "noninteractive"},
        }
        assert m_subp.call_args == mock.call(**expected_call)

    @mock.patch(
        "cloudinit.distros.debian.Distro._apt_lock_available",
        side_effect=[False, False, True],
    )
    @mock.patch("cloudinit.distros.debian.time.sleep")
    def test_wait_for_lock(self, m_sleep, m_apt_avail, m_subp, m_which):
        self.distro._wait_for_apt_command("stub", {"args": "stub2"})
        assert m_sleep.call_args_list == [mock.call(1), mock.call(1)]
        assert m_subp.call_args_list == [mock.call(args="stub2")]

    @mock.patch(
        "cloudinit.distros.debian.Distro._apt_lock_available",
        return_value=False,
    )
    @mock.patch("cloudinit.distros.debian.time.sleep")
    @mock.patch("cloudinit.distros.debian.time.time", side_effect=count())
    def test_lock_wait_timeout(
        self, m_time, m_sleep, m_apt_avail, m_subp, m_which
    ):
        with pytest.raises(TimeoutError):
            self.distro._wait_for_apt_command("stub", "stub2", timeout=5)
        assert m_subp.call_args_list == []

    @mock.patch(
        "cloudinit.distros.debian.Distro._apt_lock_available",
        side_effect=cycle([True, False]),
    )
    @mock.patch("cloudinit.distros.debian.time.sleep")
    def test_lock_exception_wait(self, m_sleep, m_apt_avail, m_subp, m_which):
        exception = subp.ProcessExecutionError(
            exit_code=100, stderr="Could not get apt lock"
        )
        m_subp.side_effect = [exception, exception, "return_thing"]
        ret = self.distro._wait_for_apt_command("stub", {"args": "stub2"})
        assert ret == "return_thing"

    @mock.patch(
        "cloudinit.distros.debian.Distro._apt_lock_available",
        side_effect=cycle([True, False]),
    )
    @mock.patch("cloudinit.distros.debian.time.sleep")
    @mock.patch("cloudinit.distros.debian.time.time", side_effect=count())
    def test_lock_exception_timeout(
        self, m_time, m_sleep, m_apt_avail, m_subp, m_which
    ):
        m_subp.side_effect = subp.ProcessExecutionError(
            exit_code=100, stderr="Could not get apt lock"
        )
        with pytest.raises(TimeoutError):
            self.distro._wait_for_apt_command(
                "stub", {"args": "stub2"}, timeout=5
            )
