# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros.arch import _render_network
from cloudinit import util

from cloudinit.tests.helpers import (CiTestCase, dir2dict)

from . import _get_distro


class TestArch(CiTestCase):

    def test_get_distro(self):
        distro = _get_distro("arch")
        hostname = "myhostname"
        hostfile = self.tmp_path("hostfile")
        distro._write_hostname(hostname, hostfile)
        self.assertEqual(hostname + "\n", util.load_file(hostfile))


class TestRenderNetwork(CiTestCase):
    def test_basic_static(self):
        """Just the most basic static config.

        note 'lo' should not be rendered as an interface."""
        entries = {'eth0': {'auto': True,
                            'dns-nameservers': ['8.8.8.8'],
                            'bootproto': 'static',
                            'address': '10.0.0.2',
                            'gateway': '10.0.0.1',
                            'netmask': '255.255.255.0'},
                   'lo': {'auto': True}}
        target = self.tmp_dir()
        devs = _render_network(entries, target=target)
        files = dir2dict(target, prefix=target)
        self.assertEqual(['eth0'], devs)
        self.assertEqual(
            {'/etc/netctl/eth0': '\n'.join([
                "Address=10.0.0.2/255.255.255.0",
                "Connection=ethernet",
                "DNS=('8.8.8.8')",
                "Gateway=10.0.0.1",
                "IP=static",
                "Interface=eth0", ""]),
             '/etc/resolv.conf': 'nameserver 8.8.8.8\n'}, files)
