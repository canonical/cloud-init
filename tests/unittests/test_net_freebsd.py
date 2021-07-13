import os
import yaml

import cloudinit.net
import cloudinit.net.network_state
from cloudinit.tests.helpers import (CiTestCase, mock, readResource, dir2dict)


SAMPLE_FREEBSD_IFCONFIG_OUT = readResource("netinfo/freebsd-ifconfig-output")
V1 = """
config:
-   id: eno1
    mac_address: 08:94:ef:51:ae:e0
    mtu: 1470
    name: eno1
    subnets:
    -   address: 172.20.80.129/25
        type: static
    type: physical
version: 1
"""


class TestInterfacesByMac(CiTestCase):

    @mock.patch('cloudinit.subp.subp')
    @mock.patch('cloudinit.util.is_FreeBSD')
    def test_get_interfaces_by_mac(self, mock_is_FreeBSD, mock_subp):
        mock_is_FreeBSD.return_value = True
        mock_subp.return_value = (SAMPLE_FREEBSD_IFCONFIG_OUT, 0)
        a = cloudinit.net.get_interfaces_by_mac()
        assert a == {'52:54:00:50:b7:0d': 'vtnet0',
                     '80:00:73:63:5c:48': 're0.33',
                     '02:14:39:0e:25:00': 'bridge0',
                     '02:ff:60:8c:f3:72': 'vnet0:11'}


class TestFreeBSDRoundTrip(CiTestCase):

    def _render_and_read(self, network_config=None, state=None,
                         netplan_path=None, target=None):
        if target is None:
            target = self.tmp_dir()
            os.mkdir("%s/etc" % target)
            with open("%s/etc/rc.conf" % target, 'a') as fd:
                fd.write("# dummy rc.conf\n")
            with open("%s/etc/resolv.conf" % target, 'a') as fd:
                fd.write("# dummy resolv.conf\n")

        if network_config:
            ns = cloudinit.net.network_state.parse_net_config_data(
                network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        renderer = cloudinit.net.freebsd.Renderer()
        renderer.render_network_state(ns, target=target)
        return dir2dict(target)

    @mock.patch('cloudinit.subp.subp')
    def test_render_output_has_yaml(self, mock_subp):

        entry = {
            'yaml': V1,
        }
        network_config = yaml.load(entry['yaml'])
        ns = cloudinit.net.network_state.parse_net_config_data(network_config)
        files = self._render_and_read(state=ns)
        assert files == {
            '/etc/resolv.conf': '# dummy resolv.conf\n',
            '/etc/rc.conf': (
                "# dummy rc.conf\n"
                "ifconfig_eno1="
                "'172.20.80.129 netmask 255.255.255.128 mtu 1470'\n")}
