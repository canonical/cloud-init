# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import shutil
import tempfile
from io import BytesIO

import pytest
from configobj import ConfigObj

from cloudinit import util
from cloudinit.config import cc_locale
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    mock,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestLocale(FilesystemMockingTestCase):
    def setUp(self):
        super(TestLocale, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        self.patchUtils(self.new_root)

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
                self.assertIn("%s UTF-8" % locale, contents)
                m_subp.assert_called_with(
                    ["localectl", "set-locale", locale], capture=False
                )

    def test_set_locale_sles(self):

        cfg = {
            "locale": "My.Locale",
        }
        cc = get_cloud("sles")
        cc_locale.handle("cc_locale", cfg, cc, [])
        if cc.distro.uses_systemd():
            locale_conf = cc.distro.systemd_locale_conf_fn
        else:
            locale_conf = cc.distro.locale_conf_fn
        contents = util.load_binary_file(locale_conf)
        n_cfg = ConfigObj(BytesIO(contents))
        if cc.distro.uses_systemd():
            self.assertEqual({"LANG": cfg["locale"]}, dict(n_cfg))
        else:
            self.assertEqual({"RC_LANG": cfg["locale"]}, dict(n_cfg))

    def test_set_locale_sles_default(self):
        cfg = {}
        cc = get_cloud("sles")
        cc_locale.handle("cc_locale", cfg, cc, [])

        if cc.distro.uses_systemd():
            locale_conf = cc.distro.systemd_locale_conf_fn
            keyname = "LANG"
        else:
            locale_conf = cc.distro.locale_conf_fn
            keyname = "RC_LANG"

        contents = util.load_binary_file(locale_conf)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({keyname: "en_US.UTF-8"}, dict(n_cfg))

    def test_locale_update_config_if_different_than_default(self):
        """Test cc_locale writes updates conf if different than default"""
        locale_conf = os.path.join(self.new_root, "etc/default/locale")
        util.write_file(locale_conf, 'LANG="en_US.UTF-8"\n')
        cfg = {"locale": "C.UTF-8"}
        cc = get_cloud("ubuntu")
        with mock.patch("cloudinit.distros.debian.subp.subp") as m_subp:
            with mock.patch(
                "cloudinit.distros.debian.LOCALE_CONF_FN", locale_conf
            ):
                cc_locale.handle("cc_locale", cfg, cc, [])
                m_subp.assert_called_with(
                    [
                        "update-locale",
                        "--locale-file=%s" % locale_conf,
                        "LANG=C.UTF-8",
                    ],
                    capture=False,
                )

    def test_locale_rhel_defaults_en_us_utf8(self):
        """Test cc_locale gets en_US.UTF-8 from distro get_locale fallback"""
        cfg = {}
        cc = get_cloud("rhel")
        update_sysconfig = "cloudinit.distros.rhel_util.update_sysconfig_file"
        with mock.patch.object(cc.distro, "uses_systemd") as m_use_sd:
            m_use_sd.return_value = True
            with mock.patch(update_sysconfig) as m_update_syscfg:
                cc_locale.handle("cc_locale", cfg, cc, [])
                m_update_syscfg.assert_called_with(
                    "/etc/locale.conf", {"LANG": "en_US.UTF-8"}
                )


class TestLocaleSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas tested via meta['examples'] in test_schema.py
            # Invalid schemas
            ({"locale": 1}, "locale: 1 is not of type 'string'"),
            (
                {"locale_configfile": 1},
                "locale_configfile: 1 is not of type 'string'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)
