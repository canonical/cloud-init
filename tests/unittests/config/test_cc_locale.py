# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2025 Raspberry Pi Ltd.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
from io import BytesIO
from pathlib import Path

import pytest
from configobj import ConfigObj

from cloudinit import util
from cloudinit.config import cc_locale
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import does_not_raise, mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@pytest.mark.usefixtures("fake_filesystem")
class TestLocale:

    def test_set_locale_arch(self):
        locale = "en_GB.UTF-8"
        locale_configfile = "/etc/invalid-locale-path"
        cfg = {
            "locale": locale,
            "locale_configfile": locale_configfile,
        }
        cc = get_cloud("arch")

        with mock.patch("cloudinit.distros.arch.subp.subp") as m_subp:
            with mock.patch("cloudinit.distros.arch.LOG.warning") as m_LOG:
                cc_locale.handle("cc_locale", cfg, cc, [])
                m_LOG.assert_called_with(
                    "Invalid locale_configfile %s, "
                    "only supported value is "
                    "/etc/locale.conf",
                    locale_configfile,
                )

                contents = util.load_text_file(cc.distro.locale_gen_fn)
                assert "%s UTF-8" % locale in contents
                m_subp.assert_called_with(
                    ["localectl", "set-locale", locale],
                    capture=False,
                )

    @pytest.mark.parametrize(
        "distro_name,uses_systemd, cfg,expected_locale",
        (
            pytest.param(
                "sles",
                True,
                {},
                {"LANG": "en_US.UTF-8"},
                id="sles_locale_defaults_systemd",
            ),
            pytest.param(
                "sles",
                False,
                {},
                {"RC_LANG": "en_US.UTF-8"},
                id="sles_locale_defaults_not_systemd",
            ),
            pytest.param(
                "sles",
                True,
                {"locale": "My.Locale"},
                {"LANG": "My.Locale"},
                id="custom_locale",
            ),
            pytest.param(
                "rhel",
                True,
                {},
                {"LANG": "en_US.UTF-8"},
                id="test_rhel_default_locale",
            ),
        ),
    )
    def test_set_locale_sles(
        self, distro_name, uses_systemd, cfg, expected_locale, mocker
    ):
        cc = get_cloud(distro_name)
        mocker.patch.object(
            cc.distro, "uses_systemd", return_value=uses_systemd
        )
        cc_locale.handle("cc_locale", cfg, cc, [])
        if uses_systemd:
            locale_conf = cc.distro.systemd_locale_conf_fn
        else:
            locale_conf = cc.distro.locale_conf_fn
        contents = util.load_binary_file(locale_conf)
        n_cfg = ConfigObj(BytesIO(contents))
        assert expected_locale == dict(n_cfg)

    def test_locale_update_config_if_different_than_default(self, tmpdir):
        """Test cc_locale writes updates conf if different than default"""
        locale_conf = tmpdir.join("etc/default/locale")
        Path(locale_conf).parent.mkdir(parents=True)
        locale_conf.write('LANG="en_US.UTF-8"\n')
        cfg = {"locale": "C.UTF-8"}
        cc = get_cloud("ubuntu")
        with mock.patch("cloudinit.distros.debian.subp.subp") as m_subp:
            with mock.patch(
                "cloudinit.distros.debian.LOCALE_CONF_FN", locale_conf.strpath
            ):
                with mock.patch(
                    "cloudinit.distros.debian.subp.which",
                    return_value="/usr/sbin/update-locale",
                ) as m_which:
                    cc_locale.handle("cc_locale", cfg, cc, [])
        m_subp.assert_called_with(
            [
                "update-locale",
                "--locale-file=%s" % locale_conf.strpath,
                "LANG=C.UTF-8",
            ],
            update_env={
                "LANG": "C.UTF-8",
                "LANGUAGE": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
            capture=False,
        )
        m_which.assert_called_once_with("update-locale")


class TestLocaleSchema:
    @pytest.mark.parametrize(
        "config, expectation",
        (
            # Valid schemas tested via meta['examples'] in test_schema.py
            # Invalid schemas
            (
                {"locale": 1},
                pytest.raises(
                    SchemaValidationError,
                    match="locale: 1 is not of type 'string'",
                ),
            ),
            (
                {"locale_configfile": 1},
                pytest.raises(
                    SchemaValidationError,
                    match="locale_configfile: 1 is not of type 'string'",
                ),
            ),
            ({"locale": False}, does_not_raise()),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation):
        schema = get_schema()
        with expectation:
            validate_cloudconfig_schema(config, schema, strict=True)
