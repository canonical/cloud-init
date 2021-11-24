# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_resolv_conf

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import util
from copy import deepcopy

from cloudinit.tests import helpers as t_help

import logging
import os
import shutil
import tempfile
from unittest import mock

LOG = logging.getLogger(__name__)


class TestResolvConf(t_help.FilesystemMockingTestCase):
    with_logs = True
    cfg = {'manage_resolv_conf': True, 'resolv_conf': {}}

    def setUp(self):
        super(TestResolvConf, self).setUp()
        self.tmp = tempfile.mkdtemp()
        util.ensure_dir(os.path.join(self.tmp, 'data'))
        self.addCleanup(shutil.rmtree, self.tmp)

    def _fetch_distro(self, kind, conf=None):
        cls = distros.fetch(kind)
        paths = helpers.Paths({'cloud_dir': self.tmp})
        conf = {} if conf is None else conf
        return cls(kind, conf, paths)

    def call_resolv_conf_handler(self, distro_name, conf, cc=None):
        if not cc:
            ds = None
            distro = self._fetch_distro(distro_name, conf)
            paths = helpers.Paths({'cloud_dir': self.tmp})
            cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc_resolv_conf.handle('cc_resolv_conf', conf, cc, LOG, [])

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_systemd_resolved(self, m_render_to_file):
        self.call_resolv_conf_handler('photon', self.cfg)

        assert [
            mock.call(mock.ANY, '/etc/systemd/resolved.conf', mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_no_param(self, m_render_to_file):
        tmp = deepcopy(self.cfg)
        self.logs.truncate(0)
        tmp.pop('resolv_conf')
        self.call_resolv_conf_handler('photon', tmp)

        self.assertIn('manage_resolv_conf True but no parameters provided',
                      self.logs.getvalue())
        assert [
            mock.call(mock.ANY, '/etc/systemd/resolved.conf', mock.ANY)
        ] not in m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_manage_resolv_conf_false(self, m_render_to_file):
        tmp = deepcopy(self.cfg)
        self.logs.truncate(0)
        tmp['manage_resolv_conf'] = False
        self.call_resolv_conf_handler('photon', tmp)
        self.assertIn("'manage_resolv_conf' present but set to False",
                      self.logs.getvalue())
        assert [
            mock.call(mock.ANY, '/etc/systemd/resolved.conf', mock.ANY)
        ] not in m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_etc_resolv_conf(self, m_render_to_file):
        self.call_resolv_conf_handler('rhel', self.cfg)

        assert [
            mock.call(mock.ANY, '/etc/resolv.conf', mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_invalid_resolve_conf_fn(self, m_render_to_file):
        ds = None
        distro = self._fetch_distro('rhel', self.cfg)
        paths = helpers.Paths({'cloud_dir': self.tmp})
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc.distro.resolve_conf_fn = 'bla'

        self.logs.truncate(0)
        self.call_resolv_conf_handler('rhel', self.cfg, cc)

        self.assertIn('No template found, not rendering resolve configs',
                      self.logs.getvalue())

        assert [
            mock.call(mock.ANY, '/etc/resolv.conf', mock.ANY)
        ] not in m_render_to_file.call_args_list

# vi: ts=4 expandtab
