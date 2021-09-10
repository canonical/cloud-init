# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit.tests.helpers import (CiTestCase, mock)


class MyBaseDistro(distros.Distro):
    # MyBaseDistro is here to test base Distro class implementations

    def __init__(self, name="basedistro", cfg=None, paths=None):
        if not cfg:
            cfg = {}
        if not paths:
            paths = {}
        super(MyBaseDistro, self).__init__(name, cfg, paths)

    def install_packages(self, pkglist):
        raise NotImplementedError()

    def _write_network(self, settings):
        raise NotImplementedError()

    def package_command(self, command, args=None, pkgs=None):
        raise NotImplementedError()

    def update_package_sources(self):
        raise NotImplementedError()

    def apply_locale(self, locale, out_fn=None):
        raise NotImplementedError()

    def set_timezone(self, tz):
        raise NotImplementedError()

    def _read_hostname(self, filename, default=None):
        raise NotImplementedError()

    def _write_hostname(self, hostname, filename):
        raise NotImplementedError()

    def _read_system_hostname(self):
        raise NotImplementedError()


class TestManageService(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestManageService, self).setUp()
        self.dist = MyBaseDistro()

    @mock.patch("cloudinit.distros.uses_systemd")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_systemctl_initcmd(self, m_subp, m_sysd):
        self.dist.init_cmd = ['systemctl']
        m_sysd.return_value = False
        self.dist.manage_service('start', 'myssh')
        m_subp.assert_called_with(['systemctl', 'start', 'myssh'],
                                  capture=True)

    @mock.patch("cloudinit.distros.uses_systemd")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_service_initcmd(self, m_subp, m_sysd):
        self.dist.init_cmd = ['service']
        m_sysd.return_value = False
        self.dist.manage_service('start', 'myssh')
        m_subp.assert_called_with(['service', 'myssh', 'start'], capture=True)

    @mock.patch("cloudinit.distros.uses_systemd")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_service(self, m_subp, m_sysd):
        self.dist.init_cmd = ['service']
        m_sysd.return_value = False
        self.dist.manage_service('start', 'myssh')
        m_subp.assert_called_with(['service', 'myssh', 'start'], capture=True)

    @mock.patch("cloudinit.distros.uses_systemd")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_systemctl(self, m_subp, m_sysd):
        self.dist.init_cmd = ['ignore']
        m_sysd.return_value = True
        self.dist.manage_service('start', 'myssh')
        m_subp.assert_called_with(['systemctl', 'start', 'myssh'],
                                  capture=True)

# vi: ts=4 sw=4 expandtab
