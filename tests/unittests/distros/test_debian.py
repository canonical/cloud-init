# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit import util
from tests.unittests.util import get_cloud

LOCALE_PATH = "/etc/default/locale"


@pytest.mark.usefixtures("fake_filesystem")
class TestDebianApplyLocale:
    @pytest.fixture
    def m_subp(self, mocker):
        mocker.patch(
            "cloudinit.distros.debian.subp.which",
            return_value="/usr/bin/locale-gen",
        )
        yield mocker.patch(
            "cloudinit.distros.debian.subp.subp", return_value=(None, None)
        )

    @pytest.fixture
    def distro(self):
        yield get_cloud(distro="debian").distro

    def test_no_rerun(self, distro, m_subp):
        """If system has defined locale, no re-run is expected."""
        locale = "en_US.UTF-8"
        util.write_file(LOCALE_PATH, "LANG=%s\n" % locale, omode="w")
        distro.apply_locale(locale, out_fn=LOCALE_PATH)
        m_subp.assert_not_called()

    @pytest.mark.parametrize(
        "which_response,install_pkgs",
        (("", ["locales"]), ("/usr/bin/update-locale", [])),
    )
    def test_no_regen_on_c_utf8(
        self, which_response, install_pkgs, distro, mocker, m_subp
    ):
        """If locale is set to C.UTF8, do not attempt to call locale-gen.

        Install locales deb package if not present and update-locale is called.
        """
        m_which = mocker.patch(
            "cloudinit.distros.debian.subp.which",
            return_value=which_response,
        )
        m_subp.return_value = (None, None)
        locale = "C.UTF-8"
        util.write_file(LOCALE_PATH, "LANG=%s\n" % "en_US.UTF-8", omode="w")
        with mock.patch.object(distro, "install_packages") as m_install:
            distro.apply_locale(locale, out_fn=LOCALE_PATH)
        assert [
            ["update-locale", f"--locale-file={LOCALE_PATH}", f"LANG={locale}"]
        ] == [p[0][0] for p in m_subp.call_args_list]
        m_which.assert_called_with("update-locale")
        if install_pkgs:
            m_install.assert_called_once_with(install_pkgs)
        else:
            m_install.assert_not_called()

    def test_rerun_if_different(self, distro, m_subp, caplog):
        """If system has different locale, locale-gen should be called."""
        locale = "en_US.UTF-8"
        util.write_file(LOCALE_PATH, "LANG=fr_FR.UTF-8", omode="w")
        distro.apply_locale(locale, out_fn=LOCALE_PATH)
        assert [
            ["locale-gen"],
            [
                "update-locale",
                f"--locale-file={LOCALE_PATH}",
                f"LANG={locale}",
            ],
        ] == [p[0][0] for p in m_subp.call_args_list]
        assert (
            "System locale set to fr_FR.UTF-8 via /etc/default/locale"
            in caplog.text
        )
        assert "Generating locales for en_US.UTF-8" in caplog.text
        assert (
            "Updating /etc/default/locale with locale setting LANG=en_US.UTF-8"
            in caplog.text
        )

    @pytest.mark.parametrize(
        "which_response,install_pkgs",
        (("", ["locales"]), ("/usr/bin/locale-gen", [])),
    )
    def test_rerun_if_no_file(
        self, which_response, install_pkgs, mocker, distro, m_subp
    ):
        """If system has no locale file, locale-gen should be called.

        Install locales package if absent and locale-gen called.
        """
        m_which = mocker.patch(
            "cloudinit.distros.debian.subp.which",
            return_value=which_response,
        )
        locale = "en_US.UTF-8"
        with mock.patch.object(distro, "install_packages") as m_install:
            distro.apply_locale(locale, out_fn=LOCALE_PATH)
        assert [
            ["locale-gen"],
            [
                "update-locale",
                f"--locale-file={LOCALE_PATH}",
                f"LANG={locale}",
            ],
        ] == [p[0][0] for p in m_subp.call_args_list]
        calls = [c.args[0] for c in m_which.call_args_list]
        # collapse consecutive duplicates from _ensure_tool re-check
        uniq: list[str] = []
        for name in calls:
            if not uniq or uniq[-1] != name:
                uniq.append(name)
        assert uniq == ["locale-gen", "update-locale"]
        if install_pkgs:
            m_install.assert_called_with(install_pkgs)
        else:
            m_install.assert_not_called()

    def test_rerun_on_unset_system_locale(self, distro, m_subp, caplog):
        """If system has unset locale, locale-gen should be called."""
        locale = "en_US.UTF-8"
        util.write_file(LOCALE_PATH, "LANG=", omode="w")
        distro.apply_locale(locale, out_fn=LOCALE_PATH)
        assert [
            ["locale-gen"],
            [
                "update-locale",
                f"--locale-file={LOCALE_PATH}",
                f"LANG={locale}",
            ],
        ] == [p[0][0] for p in m_subp.call_args_list]
        assert (
            "System locale not found in /etc/default/locale. Assuming system "
            "locale is C.UTF-8 based on hardcoded default" in caplog.text
        )
        assert "Generating locales for en_US.UTF-8" in caplog.text
        assert (
            "Updating /etc/default/locale with locale setting LANG=en_US.UTF-8"
            in caplog.text
        )

    def test_rerun_on_mismatched_keys(self, distro, m_subp):
        """If key is LC_ALL and system has only LANG, rerun is expected."""
        locale = "en_US.UTF-8"
        util.write_file(LOCALE_PATH, "LANG=", omode="w")
        distro.apply_locale(locale, out_fn=LOCALE_PATH, keyname="LC_ALL")
        assert [
            ["locale-gen"],
            [
                "update-locale",
                f"--locale-file={LOCALE_PATH}",
                f"LC_ALL={locale}",
            ],
        ] == [p[0][0] for p in m_subp.call_args_list]

    def test_falseish_locale_raises_valueerror(self, distro, m_subp):
        """locale as None or "" is invalid and should raise ValueError."""

        with pytest.raises(
            ValueError, match="Failed to provide locale value."
        ):
            distro.apply_locale(None)
            m_subp.assert_not_called()

        with pytest.raises(
            ValueError, match="Failed to provide locale value."
        ):
            distro.apply_locale("")
            m_subp.assert_not_called()


@pytest.mark.usefixtures("fake_filesystem")
class TestLookupSupportedI18nValue:
    """Test _lookup_supported_i18n_value function."""

    def test_no_match_constructs_default(self, mocker):
        """When no match is found in SUPPORTED, construct a default line."""
        from cloudinit.distros.debian import _lookup_supported_i18n_value

        # Mock SUPPORTED file to be empty
        mocker.patch(
            "cloudinit.distros.debian.util.load_text_file",
            side_effect=OSError("File not found"),
        )

        # Request a locale that won't be found
        result = _lookup_supported_i18n_value("xyz_XY.UTF-8")
        assert result == "xyz_XY.UTF-8 UTF-8"

        # Without charset, should default to UTF-8
        result = _lookup_supported_i18n_value("abc_AB")
        assert result == "abc_AB.UTF-8 UTF-8"

        # With explicit charset
        result = _lookup_supported_i18n_value("def_DE.ISO-8859-1")
        assert result == "def_DE.ISO-8859-1 ISO-8859-1"

    def test_formats_with_charset_and_modifier(self, mocker):
        """Test various locale formats: prefix, charset, and modifier."""
        from cloudinit.distros.debian import _lookup_supported_i18n_value

        # Mock SUPPORTED file with various locale formats
        supported_content = """# Supported locales
en_US.UTF-8 UTF-8
fi_FI.ISO-8859-1 ISO-8859-1
fi_FI.UTF-8 UTF-8
it_IT@euro ISO-8859-15
ca_ES@valencia.UTF-8 UTF-8
de_DE.UTF-8 UTF-8
  fr_FR.UTF-8 UTF-8
"""
        mocker.patch(
            "cloudinit.distros.debian.util.load_text_file",
            return_value=supported_content,
        )

        # Test modifier without explicit charset: it_IT@euro
        result = _lookup_supported_i18n_value("it_IT@euro")
        assert result == "it_IT@euro ISO-8859-15"

        # Test charset without modifier: fi_FI.ISO-8859-1
        result = _lookup_supported_i18n_value("fi_FI.ISO-8859-1")
        assert result == "fi_FI.ISO-8859-1 ISO-8859-1"

        # Test both charset and modifier: ca_ES@valencia.UTF-8
        result = _lookup_supported_i18n_value("ca_ES@valencia.UTF-8")
        assert result == "ca_ES@valencia.UTF-8 UTF-8"

        # Test bare locale preferring UTF-8
        result = _lookup_supported_i18n_value("fi_FI")
        assert result == "fi_FI.UTF-8 UTF-8"

        # Test that lines with leading whitespace are matched (then stripped)
        result = _lookup_supported_i18n_value("fr_FR.UTF-8")
        assert result == "fr_FR.UTF-8 UTF-8"
