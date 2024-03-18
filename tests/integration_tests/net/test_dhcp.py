"""Integration tests related to cloud-init dhcp."""

import pytest

from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU, NOBLE
from tests.integration_tests.util import verify_clean_log


@pytest.mark.skipif(not IS_UBUNTU, reason="ubuntu-specific tests")
@pytest.mark.skipif(
    PLATFORM not in ["azure", "ec2", "gce", "openstack"],
    reason="not all platforms require dhcp",
)
class TestDHCP:
    """Integration tests relating to dhcp"""

    @pytest.mark.skipif(
        CURRENT_RELEASE >= NOBLE, reason="noble and later use dhcpcd"
    )
    def test_old_ubuntu_uses_isc_dhclient_by_default(self, client):
        """verify that old releases use dhclient"""
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "DHCP client selected: dhclient" in log
        verify_clean_log(log)

    @pytest.mark.xfail(
        reason=(
            "Noble images have dhclient installed and ordered first in their"
            "configuration. Until this changes, dhcpcd will not be used"
        )
    )
    @pytest.mark.skipif(
        CURRENT_RELEASE < NOBLE, reason="pre-noble uses dhclient"
    )
    def test_noble_and_newer_uses_dhcpcd_by_default(self, client):
        """verify that noble will use dhcpcd"""
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "DHCP client selected: dhcpcd" in log
        assert (
            ", DHCP is still running" not in log
        ), "cloud-init leaked a dhcp daemon that is still running"
        verify_clean_log(log)

    @pytest.mark.skipif(
        CURRENT_RELEASE < NOBLE,
        reason="earlier Ubuntu releases have a package named dhcpcd5",
    )
    @pytest.mark.parametrize(
        "dhcp_client, package",
        [
            ("dhcpcd", "dhcpcd-base"),
            ("udhcpc", "udhcpc"),
        ],
    )
    def test_noble_and_newer_force_client(self, client, dhcp_client, package):
        """force noble to use dhcpcd and test that it worked"""
        assert client.execute(f"apt update && apt install -yq {package}").ok
        assert client.execute(
            "sed -i 's|"
            "dhcp_client_priority.*$"
            f"|dhcp_client_priority: [{dhcp_client}]"
            "|' /etc/cloud/cloud.cfg"
        ).ok
        client.execute("cloud-init clean --logs")
        client.restart()
        log = client.read_from_file("/var/log/cloud-init.log")
        for line in log.split("\n"):
            if "DHCP client selected" in line:
                assert (
                    f"DHCP client selected: {dhcp_client}" in line
                ), f"Selected incorrect dhcp client: {line}"
                break
        else:
            assert False, "No dhcp client selected"
        assert "Received dhcp lease on" in log, "No lease received"
        assert (
            ", DHCP is still running" not in log
        ), "cloud-init leaked a dhcp daemon that is still running"
        if not "ec2" == PLATFORM:
            assert "Received dhcp lease on " in log, "EphemeralDHCPv4 failed"
        if "azure" == PLATFORM:
            if "udhcpc" == dhcp_client:
                pytest.xfail(
                    "udhcpc implementation doesn't support azure, see GH-4765"
                )
            assert (
                "Obtained DHCP lease on interface" in log
            ), "Failed to get unknown option 245"
            assert "'unknown-245'" in log, "Failed to get unknown option 245"
        verify_clean_log(log)
