# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_locale

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util

from cloudinit.sources import DataSourceNoCloud

from cloudinit.tests import helpers as t_help

from configobj import ConfigObj

from six import BytesIO

import logging
import mock
import os
import shutil
import tempfile

LOG = logging.getLogger(__name__)


class TestLocale(t_help.FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestLocale, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})

        cls = distros.fetch(distro)
        d = cls(distro, {}, paths)
        ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
        cc = cloud.Cloud(ds, paths, {}, d, None)
        return cc

    def test_set_locale_sles(self):

        cfg = {
            'locale': 'My.Locale',
        }
        cc = self._get_cloud('sles')
        cc_locale.handle('cc_locale', cfg, cc, LOG, [])
        if cc.distro.uses_systemd():
            locale_conf = cc.distro.systemd_locale_conf_fn
        else:
            locale_conf = cc.distro.locale_conf_fn
        contents = util.load_file(locale_conf, decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        if cc.distro.uses_systemd():
            self.assertEqual({'LANG': cfg['locale']}, dict(n_cfg))
        else:
            self.assertEqual({'RC_LANG': cfg['locale']}, dict(n_cfg))

    def test_set_locale_sles_default(self):
        cfg = {}
        cc = self._get_cloud('sles')
        cc_locale.handle('cc_locale', cfg, cc, LOG, [])

        if cc.distro.uses_systemd():
            locale_conf = cc.distro.systemd_locale_conf_fn
            keyname = 'LANG'
        else:
            locale_conf = cc.distro.locale_conf_fn
            keyname = 'RC_LANG'

        contents = util.load_file(locale_conf, decode=False)
        n_cfg = ConfigObj(BytesIO(contents))
        self.assertEqual({keyname: 'en_US.UTF-8'}, dict(n_cfg))

    def test_locale_update_config_if_different_than_default(self):
        """Test cc_locale writes updates conf if different than default"""
        locale_conf = os.path.join(self.new_root, "etc/default/locale")
        util.write_file(locale_conf, 'LANG="en_US.UTF-8"\n')
        cfg = {'locale': 'C.UTF-8'}
        cc = self._get_cloud('ubuntu')
        with mock.patch('cloudinit.distros.debian.util.subp') as m_subp:
            with mock.patch('cloudinit.distros.debian.LOCALE_CONF_FN',
                            locale_conf):
                cc_locale.handle('cc_locale', cfg, cc, LOG, [])
                m_subp.assert_called_with(['update-locale',
                                           '--locale-file=%s' % locale_conf,
                                           'LANG=C.UTF-8'], capture=False)

    def test_locale_rhel_defaults_en_us_utf8(self):
        """Test cc_locale gets en_US.UTF-8 from distro get_locale fallback"""
        cfg = {}
        cc = self._get_cloud('rhel')
        update_sysconfig = 'cloudinit.distros.rhel_util.update_sysconfig_file'
        with mock.patch.object(cc.distro, 'uses_systemd') as m_use_sd:
            m_use_sd.return_value = True
            with mock.patch(update_sysconfig) as m_update_syscfg:
                cc_locale.handle('cc_locale', cfg, cc, LOG, [])
                m_update_syscfg.assert_called_with('/etc/locale.conf',
                                                   {'LANG': 'en_US.UTF-8'})


# vi: ts=4 expandtab
