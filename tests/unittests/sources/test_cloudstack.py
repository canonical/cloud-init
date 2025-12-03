# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init
from socket import gaierror
from textwrap import dedent

import pytest

from cloudinit import helpers
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.sources import DataSourceHostname
from cloudinit.sources.DataSourceCloudStack import (
    CLOUD_STACK_DMI_NAME,
    DataSourceCloudStack,
    DataSourceCloudStackLocal,
    get_data_server,
    get_vr_address,
)
from tests.unittests.helpers import mock
from tests.unittests.util import MockDistro

SOURCES_PATH = "cloudinit.sources"
MOD_PATH = SOURCES_PATH + ".DataSourceCloudStack"
DS_PATH = MOD_PATH + ".DataSourceCloudStack"
DHCP_MOD_PATH = "cloudinit.net.dhcp"
FAKE_LEASE = {
    "interface": "eth0",
    "fixed-address": "192.168.0.1",
    "subnet-mask": "255.255.255.0",
    "routers": "192.168.0.1",
    "domain-name": "dhclient.local",
    "renew": "4 2017/07/27 18:02:30",
    "expire": "5 2017/07/28 07:08:15",
}

FAKE_LEASE_WITH_SERVER_IDENT = """\
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
  option rfc3442-classless-static-routes 0,10,0,0,1,32,168,63,129,16,10,0,0,1,32,169,254,169,254,10,0,0,1;
  option unknown-245 a8:3f:81:10;
  option dhcp-rebinding-time 4294967295;
  renew 0 2160/02/17 02:22:33;
  rebind 0 2160/02/17 02:22:33;
  expire 0 2160/02/17 02:22:33;
}
"""  # noqa: E501


@pytest.fixture
def cloudstack_ds(request, paths):
    yield DataSourceCloudStack(sys_cfg={}, distro=MockDistro(), paths=paths)


@pytest.mark.usefixtures("dhclient_exists")
class TestCloudStackHostname:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmp_path):
        self.hostname = "vm-hostname"
        self.networkd_domainname = "networkd.local"
        self.isc_dhclient_domainname = "dhclient.local"

        get_hostname_parent = mock.MagicMock(
            return_value=DataSourceHostname(self.hostname, True)
        )
        mocker.patch(
            SOURCES_PATH + ".DataSource.get_hostname", get_hostname_parent
        )
        mocker.patch(
            DHCP_MOD_PATH + ".util.load_text_file",
            return_value=FAKE_LEASE_WITH_SERVER_IDENT,
        )
        # Mock cloudinit.net.dhcp.networkd_get_option_from_leases() method \
        # result since we don't have a DHCP client running
        networkd_get_option_from_leases = mock.MagicMock(
            return_value=self.networkd_domainname
        )
        mocker.patch(
            DHCP_MOD_PATH + ".networkd_get_option_from_leases",
            networkd_get_option_from_leases,
        )

    def test_get_domainname_networkd(self, cloudstack_ds):
        """
        Test if DataSourceCloudStack._get_domainname()
        gets domain name from systemd-networkd leases.
        """
        assert self.networkd_domainname == cloudstack_ds._get_domainname()

    def test_get_domainname_isc_dhclient(self, cloudstack_ds, mocker):
        """
        Test if DataSourceCloudStack._get_domainname()
        gets domain name from isc-dhcp-client leases
        """

        # Override systemd-networkd reply mock to None
        # to force the code to fallback to IscDhclient
        get_networkd_domain = mock.MagicMock(return_value=None)
        mocker.patch(
            DHCP_MOD_PATH + ".networkd_get_option_from_leases",
            get_networkd_domain,
        )

        with mocker.patch(
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
            result = cloudstack_ds._get_domainname()
        assert self.isc_dhclient_domainname == result

    def test_get_hostname_non_fqdn(self, cloudstack_ds):
        """
        Test get_hostname() method implementation
        with fqdn parameter=False.
        It should call the parent class method and should
        return its response intact.
        """
        expected = DataSourceHostname(self.hostname, True)
        result = cloudstack_ds.get_hostname(fqdn=False)
        assert expected == result

    def test_get_hostname_fqdn(self, cloudstack_ds):
        """
        Test get_hostname() method implementation
        with fqdn parameter=True.
        It should look for domain name in DHCP leases.
        """
        expected = DataSourceHostname(
            self.hostname + "." + self.networkd_domainname, True
        )
        result = cloudstack_ds.get_hostname(fqdn=True)
        assert expected == result

    def test_get_hostname_fqdn_fallback(self, cloudstack_ds, mocker):
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
        mocker.patch(
            DHCP_MOD_PATH + ".networkd_get_option_from_leases",
            get_networkd_domain,
        )

        mocker.patch(
            "cloudinit.distros.net.find_fallback_nic",
            return_value="eth0",
        )

        mocker.patch(
            MOD_PATH + ".dhcp.IscDhclient.get_newest_lease_file_from_distro",
            return_value=True,
        )

        mocker.patch(
            MOD_PATH + ".dhcp.IscDhclient.parse_leases", return_value=[]
        )

        lease = {
            "interface": "eth0",
            "fixed-address": "192.168.0.1",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.0.1",
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        mocker.patch(
            DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
            return_value=lease,
        )
        mocker.patch(
            DHCP_MOD_PATH + ".Dhcpcd.get_newest_lease", return_value=lease
        )

        cloudstack_ds.distro.fallback_interface = "eth0"
        with mocker.patch(MOD_PATH + ".util.load_text_file"):
            result = cloudstack_ds.get_hostname(fqdn=True)
            assert expected == result


class TestGetDataServer:
    @pytest.mark.parametrize(
        "addrinfo,expected,expected_log",
        (
            pytest.param(
                # Fake addrinfo
                [("_", "_", "_", "_", ("10.1.35.171", 80)), "_"],
                "10.1.35.171",
                None,
                id="success_on_dns_resolution",
            ),
            pytest.param(
                gaierror("Name or service not known"),
                None,
                "DNS Entry data-server not found",
                id="none_on_no_dns_resolution",
            ),
        ),
    )
    def test_data_server_from_dns(
        self, addrinfo, expected, expected_log, mocker, caplog
    ):
        """Lookup data-server from DNS."""
        if isinstance(addrinfo, Exception):
            mocker.patch(MOD_PATH + ".getaddrinfo", side_effect=addrinfo)
            assert expected == get_data_server()
        else:
            mocker.patch(MOD_PATH + ".getaddrinfo", return_value=addrinfo)
            assert expected is get_data_server()
        if expected_log:
            assert expected_log in caplog.text


@mock.patch(MOD_PATH + ".get_data_server", return_value="10.1.37.131")
@mock.patch(
    MOD_PATH + ".dhcp.networkd_get_option_from_leases",
    return_value="10.1.37.132",
)
class TestGetVrAddress:
    def test_get_vr_addr_from_dns(
        self, m_networkd_option_from_leases, m_get_data_server, caplog
    ):
        """cloud-init first obtains data-server if resolved by DNS"""
        assert "10.1.37.131" == get_vr_address(MockDistro())
        assert (
            "Found metadata server '10.1.37.131' via data-server DNS entry"
            in caplog.text
        )
        assert 0 == m_networkd_option_from_leases.call_count

    def test_get_vr_addr_from_networkd_leases(
        self, m_networkd_option_from_leases, m_get_data_server, mocker, caplog
    ):
        """When no DNS for data-server use networkd dhcp-server-identifier"""
        mocker.patch(MOD_PATH + ".get_data_server", return_value=None)
        assert "10.1.37.132" == get_vr_address(MockDistro())
        assert (
            "Found SERVER_ADDRESS '10.1.37.132' via networkd_leases"
            in caplog.text
        )
        m_networkd_option_from_leases.assert_called_once_with("SERVER_ADDRESS")


@pytest.mark.usefixtures("dhclient_exists")
@mock.patch(MOD_PATH + ".dmi.read_dmi_data", return_value=CLOUD_STACK_DMI_NAME)
class TestCloudStackPasswordFetching:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmp_path):
        mocker.patch(f"{MOD_PATH}.ec2")
        mocker.patch(f"{MOD_PATH}.uhelp")
        default_gw = "192.201.20.0"
        mocker.patch(
            DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
            return_value={
                "interface": "eth0",
                "fixed-address": "192.168.0.1",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.0.1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
                "dhcp-server-identifier": "168.63.129.16",
            },
        )
        get_newest_lease_file_from_distro = mock.MagicMock(return_value=None)
        mocker.patch(
            DHCP_MOD_PATH + ".IscDhclient.get_newest_lease",
            return_value={
                "interface": "eth0",
                "fixed-address": "192.168.0.1",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.0.1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
                "dhcp-server-identifier": "168.63.129.16",
            },
        )
        mocker.patch(
            DHCP_MOD_PATH + ".IscDhclient.get_newest_lease_file_from_distro",
            get_newest_lease_file_from_distro,
        )
        get_default_gw = mock.MagicMock(return_value=default_gw)
        mocker.patch(MOD_PATH + ".get_default_gateway", get_default_gw)

        get_networkd_server_address = mock.MagicMock(return_value=None)
        mocker.patch(
            MOD_PATH + ".dhcp.networkd_get_option_from_leases",
            get_networkd_server_address,
        )
        get_data_server = mock.MagicMock(return_value=None)
        mocker.patch(MOD_PATH + ".get_data_server", get_data_server)

    def _set_password_server_response(self, response_string, mocker):
        fake_resp = mock.MagicMock()
        fake_resp.contents = response_string.encode("utf-8")
        readurl_mock = mocker.patch(
            "cloudinit.sources.DataSourceCloudStack.uhelp.readurl",
            return_value=fake_resp,
        )
        return readurl_mock

    def test_empty_password_doesnt_create_config(
        self, _dmi, cloudstack_ds, mocker
    ):
        self._set_password_server_response("", mocker)
        cloudstack_ds.get_data()
        assert {} == cloudstack_ds.get_config_obj()

    def test_saved_password_doesnt_create_config(
        self, _dmi, cloudstack_ds, mocker
    ):
        self._set_password_server_response("saved_password", mocker)
        cloudstack_ds.get_data()
        assert {} == cloudstack_ds.get_config_obj()

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_password_sets_password(self, m_wait, _dmi, cloudstack_ds, mocker):
        m_wait.return_value = True
        password = "SekritSquirrel"
        self._set_password_server_response(password, mocker)
        cloudstack_ds.get_data()
        assert password == cloudstack_ds.get_config_obj()["password"]

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_bad_request_doesnt_stop_ds_from_working(
        self, m_wait, _dmi, cloudstack_ds, mocker
    ):
        m_wait.return_value = True
        self._set_password_server_response("bad_request", mocker)
        assert cloudstack_ds.get_data() is True

    def assertRequestTypesSent(self, readurl, expected_request_types):
        request_types = []
        for call in readurl.call_args_list:
            headers = call.kwargs.get("headers", {})
            domu_req = headers.get("DomU_Request")
            if domu_req:
                request_types.append(domu_req)
        assert expected_request_types == request_types

    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    def test_valid_response_means_password_marked_as_saved(
        self, m_wait, _dmi, cloudstack_ds, mocker
    ):
        m_wait.return_value = True
        password = "SekritSquirrel"
        readurl = self._set_password_server_response(password, mocker)
        cloudstack_ds.get_data()
        self.assertRequestTypesSent(
            readurl, ["send_my_password", "saved_password"]
        )

    def _check_password_not_saved_for(
        self, response_string, cloudstack_ds, mocker
    ):
        readurl = self._set_password_server_response(
            response_string, mocker=mocker
        )
        with mock.patch(DS_PATH + ".wait_for_metadata_service") as m_wait:
            m_wait.return_value = True
            cloudstack_ds.get_data()
        self.assertRequestTypesSent(readurl, ["send_my_password"])

    def test_password_not_saved_if_empty(self, _dmi, cloudstack_ds, mocker):
        self._check_password_not_saved_for("", cloudstack_ds, mocker)

    def test_password_not_saved_if_already_saved(
        self, _dmi, cloudstack_ds, mocker
    ):
        self._check_password_not_saved_for(
            "saved_password", cloudstack_ds, mocker
        )

    def test_password_not_saved_if_bad_request(
        self, _dmi, cloudstack_ds, mocker
    ):
        self._check_password_not_saved_for(
            "bad_request", cloudstack_ds, mocker
        )


class TestDataSourceCloudStackLocal:

    @mock.patch(MOD_PATH + ".EphemeralIPNetwork", autospec=True)
    @mock.patch(MOD_PATH + ".net.find_fallback_nic")
    @mock.patch(MOD_PATH + ".get_vr_address", return_value="10.1.37.131")
    def test_local_datasource_fails_ephemeral_dhcp(
        self, m_get_vr_address, m_find_fallback_nic, m_dhcp, caplog, tmpdir
    ):
        distro = MockDistro()
        ds = DataSourceCloudStackLocal(
            {}, distro, helpers.Paths({"run_dir": tmpdir})
        )
        fallback_nic_cases = ["enp0s1", "enp0s1"]
        dhcp_results = [NoDHCPLeaseError, Exception("Something unexpected")]
        expected_logs = [
            (
                "Attempting DHCP on: enp0s1",
                "Unable to obtain a DHCP lease on enp0s1",
            ),
            (
                "Attempting DHCP on: enp0s1",
                "Failed fetching metadata service: Something unexpected",
            ),
        ]

        # Each of the above cases, except the first, increments the m_dhcp call
        # count by one. Therefore start at and expect 0, incrementing the
        # expectation with each iteration
        dhcp_module_call_count = 0
        for fallback_nic, dhcp_result, logs in zip(
            fallback_nic_cases, dhcp_results, expected_logs
        ):
            m_find_fallback_nic.return_value = fallback_nic
            m_dhcp.return_value.__enter__.side_effect = dhcp_result
            dhcp_module_call_count += 1
            assert m_dhcp.call_count == dhcp_module_call_count - 1
            assert ds._get_data() is False
            for msg in logs:
                assert msg in caplog.text

    @mock.patch(MOD_PATH + ".CloudStackPasswordServerClient.get_password")
    @mock.patch(SOURCES_PATH + ".helpers.ec2.get_instance_metadata")
    @mock.patch(SOURCES_PATH + ".helpers.ec2.get_instance_userdata")
    @mock.patch(DS_PATH + ".wait_for_metadata_service")
    @mock.patch(
        MOD_PATH + ".EphemeralIPNetwork",
        autospec=True,
    )
    @mock.patch(MOD_PATH + ".net.find_fallback_nic")
    # @mock.patch(MOD_PATH + ".get_vr_address", return_value="10.1.37.131")
    def test_local_datasource_success(
        self,
        # m_get_vr_address,
        m_find_fallback_nic,
        m_dhcp,
        m_wait_for_mds,
        m_get_userdata,
        m_get_metadata,
        m_get_password,
        tmpdir,
    ):
        distro = MockDistro()
        ds = DataSourceCloudStackLocal(
            {}, distro, helpers.Paths({"run_dir": tmpdir})
        )

        m_find_fallback_nic.return_value = "enp0s1"
        m_dhcp.return_value.__enter__.side_effect = (None,)
        m_wait_for_mds.return_value = (True,)
        m_get_userdata.return_value = "ud"
        m_get_metadata.return_value = "md"
        m_get_password.return_value = True

        assert ds._get_data() is True
        assert ds.userdata_raw == "ud"
        assert ds.metadata == "md"
