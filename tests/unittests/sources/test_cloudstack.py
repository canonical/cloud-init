# This file is part of cloud-init. See LICENSE file for license information.
from textwrap import dedent

import pytest

from cloudinit import helpers
from cloudinit.distros import rhel, ubuntu
from cloudinit.sources import DataSourceHostname
from cloudinit.sources.DataSourceCloudStack import DataSourceCloudStack
from tests.unittests.helpers import CiTestCase, ExitStack, mock
from tests.unittests.util import MockDistro

SOURCES_PATH = "cloudinit.sources"
MOD_PATH = SOURCES_PATH + ".DataSourceCloudStack"
DS_PATH = MOD_PATH + ".DataSourceCloudStack"
DHCP_MOD_PATH = "cloudinit.net.dhcp"


@pytest.mark.usefixtures("dhclient_exists")
class TestCloudStackHostname(CiTestCase):
    def setUp(self):
        super(TestCloudStackHostname, self).setUp()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.hostname = "vm-hostname"
        self.networkd_domainname = "networkd.local"
        self.isc_dhclient_domainname = "dhclient.local"

        # Mock the parent class get_hostname() method to return
        # a non-fqdn hostname
        get_hostname_parent = mock.MagicMock(
            return_value=DataSourceHostname(self.hostname, True)
        )
        self.patches.enter_context(
            mock.patch(
                SOURCES_PATH + ".DataSource.get_hostname", get_hostname_parent
            )
        )
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".util.load_text_file",
                return_value=dedent(
                    """
                    lease {
                      interface "eth0";
                      fixed-address 10.0.0.5;
                      server-name "DSM111070915004";
                      option subnet-mask 255.255.255.0;
                      option dhcp-lease-time 4294967295;
                      option routers 10.0.0.1;
                      option dhcp-message-type 5;
                      option dhcp-server-identifier 168.63.129.16;
                      option domain-name-servers 168.63.129.16;
                      option dhcp-renewal-time 4294967295;
                      option rfc3442-classless-static-routes """
                    """0,10,0,0,1,32,168,63,129,16,10,0,0,1,32,169,254,"""
                    """169,254,10,0,0,1;
                      option unknown-245 a8:3f:81:10;
                      option dhcp-rebinding-time 4294967295;
                    """
                    """renew 0 2160/02/17 02:22:33;
                      rebind 0 2160/02/17 02:22:33;
                      expire 0 2160/02/17 02:22:33;
                    }
                    """
                ),
            )
        )

        # Mock cloudinit.net.dhcp.networkd_get_option_from_leases() method \
        # result since we don't have a DHCP client running
        networkd_get_option_from_leases = mock.MagicMock(
            return_value=self.networkd_domainname
        )
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".networkd_get_option_from_leases",
                networkd_get_option_from_leases,
            )
        )

        # Mock cloudinit.net.dhcp.get_newest_lease_file_from_distro() method \
        # result since we don't have a DHCP client running
        isc_dhclient_get_newest_lease_file_from_distro = mock.MagicMock(
            return_value="/var/lib/NetworkManager/dhclient-u-u-i-d-eth0.lease"
        )
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH
                + ".IscDhclient.get_newest_lease_file_from_distro",
                isc_dhclient_get_newest_lease_file_from_distro,
            )
        )

        # Mock cloudinit.net.dhcp.networkd_get_option_from_leases() method \
        # result since we don't have a DHCP client running
        lease = {
            "interface": "eth0",
            "fixed-address": "192.168.0.1",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.0.1",
            "domain-name": self.isc_dhclient_domainname,
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        get_newest_lease = mock.MagicMock(return_value=lease)

        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
                get_newest_lease,
            )
        )

        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".IscDhclient.parse_leases",
                mock.MagicMock(return_value=[lease]),
            )
        )

        # Mock get_vr_address() method as it relies to
        # parsing DHCP/networkd files
        self.patches.enter_context(
            mock.patch(
                MOD_PATH + ".get_vr_address",
                mock.MagicMock(return_value="192.168.0.1"),
            )
        )

        self.tmp = self.tmp_dir()

    def test_get_domainname_networkd(self):
        """
        Test if DataSourceCloudStack._get_domainname()
        gets domain name from systemd-networkd leases.
        """
        ds = DataSourceCloudStack(
            {}, ubuntu.Distro, helpers.Paths({"run_dir": self.tmp})
        )
        result = ds._get_domainname()
        self.assertEqual(self.networkd_domainname, result)

    def test_get_domainname_isc_dhclient(self):
        """
        Test if DataSourceCloudStack._get_domainname()
        gets domain name from isc-dhcp-client leases
        """

        # Override systemd-networkd reply mock to None
        # to force the code to fallback to IscDhclient
        get_networkd_domain = mock.MagicMock(return_value=None)
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".networkd_get_option_from_leases",
                get_networkd_domain,
            )
        )

        ds = DataSourceCloudStack(
            {}, rhel.Distro, helpers.Paths({"run_dir": self.tmp})
        )
        with mock.patch(
            MOD_PATH + ".util.load_text_file",
            return_value=dedent(
                """
                lease {
                  interface "eth0";
                  fixed-address 10.0.0.5;
                  server-name "DSM111070915004";
                  option subnet-mask 255.255.255.0;
                  option dhcp-lease-time 4294967295;
                  option routers 10.0.0.1;
                  option dhcp-message-type 5;
                  option dhcp-server-identifier 168.63.129.16;
                  option domain-name-servers 168.63.129.16;
                  option dhcp-renewal-time 4294967295;
                  option rfc3442-classless-static-routes """
                """0,10,0,0,1,32,168,63,129,16,10,0,0,1,32,169,254,"""
                """169,254,10,0,0,1;
                  option unknown-245 a8:3f:81:10;
                  option dhcp-rebinding-time 4294967295;
                """
                f"option domain-name {self.isc_dhclient_domainname};"
                """renew 0 2160/02/17 02:22:33;
                  rebind 0 2160/02/17 02:22:33;
                  expire 0 2160/02/17 02:22:33;
                }
                """
            ),
        ):
            result = ds._get_domainname()
        self.assertEqual(self.isc_dhclient_domainname, result)

    def test_get_hostname_non_fqdn(self):
        """
        Test get_hostname() method implementation
        with fqdn parameter=False.
        It should call the parent class method and should
        return its response intact.
        """
        expected = DataSourceHostname(self.hostname, True)

        ds = DataSourceCloudStack(
            {}, ubuntu.Distro, helpers.Paths({"run_dir": self.tmp})
        )
        result = ds.get_hostname(fqdn=False)
        self.assertTupleEqual(expected, result)

    def test_get_hostname_fqdn(self):
        """
        Test get_hostname() method implementation
        with fqdn parameter=True.
        It should look for domain name in DHCP leases.
        """
        expected = DataSourceHostname(
            self.hostname + "." + self.networkd_domainname, True
        )

        ds = DataSourceCloudStack(
            {}, ubuntu.Distro, helpers.Paths({"run_dir": self.tmp})
        )
        result = ds.get_hostname(fqdn=True)
        self.assertTupleEqual(expected, result)

    def test_get_hostname_fqdn_fallback(self):
        """
        Test get_hostname() when some error happens
        during domainname discovery.

        We mock both systemd-networkd discovery as None,
        And the IscDhclient not having domain-name option
        in the lease.

        It should return the hostname without domainname
        in such cases.
        """
        expected = DataSourceHostname(self.hostname, True)

        # Override systemd-networkd reply mock to None
        # to force the code to fallback to IscDhclient
        get_networkd_domain = mock.MagicMock(return_value=None)
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".networkd_get_option_from_leases",
                get_networkd_domain,
            )
        )

        self.patches.enter_context(
            mock.patch(
                "cloudinit.distros.net.find_fallback_nic",
                return_value="eth0",
            )
        )

        self.patches.enter_context(
            mock.patch(
                MOD_PATH
                + ".dhcp.IscDhclient.get_newest_lease_file_from_distro",
                return_value=True,
            )
        )

        self.patches.enter_context(
            mock.patch(
                MOD_PATH + ".dhcp.IscDhclient.parse_leases", return_value=[]
            )
        )

        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
                return_value={
                    "interface": "eth0",
                    "fixed-address": "192.168.0.1",
                    "subnet-mask": "255.255.255.0",
                    "routers": "192.168.0.1",
                    "renew": "4 2017/07/27 18:02:30",
                    "expire": "5 2017/07/28 07:08:15",
                },
            )
        )

        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".util.load_text_file",
                return_value=dedent(
                    """
                    lease {
                      interface "eth0";
                      fixed-address 10.0.0.5;
                      server-name "DSM111070915004";
                      option subnet-mask 255.255.255.0;
                      option dhcp-lease-time 4294967295;
                      option routers 10.0.0.1;
                      option dhcp-message-type 5;
                      option dhcp-server-identifier 168.63.129.16;
                      option domain-name-servers 168.63.129.16;
                      option dhcp-renewal-time 4294967295;
                      option rfc3442-classless-static-routes """
                    """0,10,0,0,1,32,168,63,129,16,10,0,0,1,32,169,254,"""
                    """169,254,10,0,0,1;
                      option unknown-245 a8:3f:81:10;
                      option dhcp-rebinding-time 4294967295;
                    """
                    """renew 0 2160/02/17 02:22:33;
                      rebind 0 2160/02/17 02:22:33;
                      expire 0 2160/02/17 02:22:33;
                    }
                    """
                ),
            )
        )

        ds = DataSourceCloudStack(
            {}, ubuntu.Distro("", {}, {}), helpers.Paths({"run_dir": self.tmp})
        )
        ds.distro.fallback_interface = "eth0"
        with mock.patch(MOD_PATH + ".util.load_text_file"):
            result = ds.get_hostname(fqdn=True)
            self.assertTupleEqual(expected, result)


@pytest.mark.usefixtures("dhclient_exists")
class TestCloudStackPasswordFetching(CiTestCase):
    def setUp(self):
        super(TestCloudStackPasswordFetching, self).setUp()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        mod_name = MOD_PATH
        self.patches.enter_context(mock.patch("{0}.ec2".format(mod_name)))
        self.patches.enter_context(mock.patch("{0}.uhelp".format(mod_name)))
        default_gw = "192.201.20.0"

        get_newest_lease_file_from_distro = mock.MagicMock(return_value=None)
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
                return_value={
                    "interface": "eth0",
                    "fixed-address": "192.168.0.1",
                    "subnet-mask": "255.255.255.0",
                    "routers": "192.168.0.1",
                    "renew": "4 2017/07/27 18:02:30",
                    "expire": "5 2017/07/28 07:08:15",
                },
            )
        )
        self.patches.enter_context(
            mock.patch(
                DHCP_MOD_PATH
                + ".IscDhclient.get_newest_lease_file_from_distro",
                get_newest_lease_file_from_distro,
            )
        )

        get_default_gw = mock.MagicMock(return_value=default_gw)
        self.patches.enter_context(
            mock.patch(mod_name + ".get_default_gateway", get_default_gw)
        )

        get_networkd_server_address = mock.MagicMock(return_value=None)
        self.patches.enter_context(
            mock.patch(
                mod_name + ".dhcp.networkd_get_option_from_leases",
                get_networkd_server_address,
            )
        )
        get_data_server = mock.MagicMock(return_value=None)
        self.patches.enter_context(
            mock.patch(mod_name + ".get_data_server", get_data_server)
        )

        self.tmp = self.tmp_dir()

    def _set_password_server_response(self, response_string):
        subp = mock.MagicMock(return_value=(response_string, ""))
        self.patches.enter_context(
            mock.patch(
                "cloudinit.sources.DataSourceCloudStack.subp.subp", subp
            )
        )
        return subp

    def test_empty_password_doesnt_create_config(self):
        self._set_password_server_response("")
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    def test_saved_password_doesnt_create_config(self):
        self._set_password_server_response("saved_password")
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        ds.get_data()
        self.assertEqual({}, ds.get_config_obj())

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_password_sets_password(self, m_wait):
        m_wait.return_value = True
        password = "SekritSquirrel"
        self._set_password_server_response(password)
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        ds.get_data()
        self.assertEqual(password, ds.get_config_obj()["password"])

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_bad_request_doesnt_stop_ds_from_working(self, m_wait):
        m_wait.return_value = True
        self._set_password_server_response("bad_request")
        # with mock.patch(DHCP_MOD_PATH + ".util.load_text_file"):
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        self.assertTrue(ds.get_data())

    def assertRequestTypesSent(self, subp, expected_request_types):
        request_types = []
        for call in subp.call_args_list:
            args = call[0][0]
            for arg in args:
                if arg.startswith("DomU_Request"):
                    request_types.append(arg.split()[1])
        self.assertEqual(expected_request_types, request_types)

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_valid_response_means_password_marked_as_saved(self, m_wait):
        m_wait.return_value = True
        password = "SekritSquirrel"
        subp = self._set_password_server_response(password)
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        ds.get_data()
        self.assertRequestTypesSent(
            subp, ["send_my_password", "saved_password"]
        )

    def _check_password_not_saved_for(self, response_string):
        subp = self._set_password_server_response(response_string)
        ds = DataSourceCloudStack(
            {}, MockDistro(), helpers.Paths({"run_dir": self.tmp})
        )
        with mock.patch(DS_PATH + ".wait_for_metadata_service") as m_wait:
            m_wait.return_value = True
            ds.get_data()
        self.assertRequestTypesSent(subp, ["send_my_password"])

    def test_password_not_saved_if_empty(self):
        self._check_password_not_saved_for("")

    def test_password_not_saved_if_already_saved(self):
        self._check_password_not_saved_for("saved_password")

    def test_password_not_saved_if_bad_request(self):
        self._check_password_not_saved_for("bad_request")
