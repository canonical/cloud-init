import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM

IPV4_METADATA_ADDRESS = "169.254.169.254"
IPV6_METADATA_ADDRESS = "fd00:c1::a9fe:a9fe"


def _find_imds_read_log(log: str, address: str) -> bool:
    """
    Check if the log contains a successful IMDS read from the given address.

    Args:
        log: Contents of the cloud-init log file to search.
        address: The IMDS IP address to look for in the log.
    """
    return (
        "Successfully fetched instance metadata from IMDS at: "
        f"http://[{address}]/" in log
    )


def _test_reading_ipv6_metadata_succeeds(client: IntegrationInstance):
    """
    Test that reading metadata succeeds for an IPv6 instance.

    This function performs the following checks:
    1. Reads the cloud-init log file and ensures that a log entry indicates
         the metadata was successfully read from the IPv6 IMDS address.
    2. Verifies that the cloud-init status indicates a successful read of
    """
    log = client.read_from_file("/var/log/cloud-init.log")
    matching_line = None
    for line in log.splitlines():
        if _find_imds_read_log(line, IPV6_METADATA_ADDRESS):
            matching_line = line
            break
    assert matching_line is not None
    assert client.execute("cloud-init status --long").ok


def _test_reading_ipv6_metadata_fails(client: IntegrationInstance):
    """
    Test that reading metadata fails for an IPv6 instance and that the fallback
    datasource is used instead.
    This function performs the following checks:
    1. Reads the cloud-init log file and ensures that no log entry indicates
       an attempt to read metadata from the IPv6 IMDS address.
    2. Verifies that the cloud-init status indicates the use of a fallback
       datasource due to the failure of IPv6 connectivity checks.
    3. Ensures that the status message confirms the failure to fetch IMDS
       metadata from the IPv6 address and instead used the fallback datasource.
    4. The cloud-init status exit code should indicate a failure.
    Args:
        client (IntegrationInstance): The integration test client instance.
        address (str): The IPv6 address to check in the cloud-init log.
    """
    log = client.read_from_file("/var/log/cloud-init.log")
    matching_line = None
    for line in log.splitlines():
        if _find_imds_read_log(line, IPV6_METADATA_ADDRESS):
            matching_line = line
            break

    # ensure that the line was NOT found
    assert matching_line is None

    # now check cloud-init status to ensure that ipv6 instance failed to
    # retrieve metadata from IMDS
    status = client.execute("cloud-init status --long")
    assert "Used fallback datasource" in status
    # since IPV6 connectivity checks will fail in Oracle Datasource,
    # we want to verify that it did NOT try querying the IPV6 address
    # and instead used the fallback datasource
    assert (
        "Failed to fetch IMDS metadata from any of: "
        f"http://{IPV4_METADATA_ADDRESS}" in status
    )
    assert not status.ok


def _install_netfilter_perstistent(client: IntegrationInstance):
    assert client.execute("sudo apt-get install -y iptables-persistent").ok


def _clean_and_wait_for_cloudinit(client: IntegrationInstance):
    """
    Clean up the instance and wait for cloud-init to finish

    This function performs the following steps:
    1. Cleans up the instance and wipes all cloud-init logs and data, and then
         reboots the instance.
    2. Waits for the instance to reboot and for cloud-init to finish running.
    """
    client.execute("cloud-init clean --logs")
    client.restart()
    # then wait on cloud-init to finish
    client.instance._wait_for_execute()


@pytest.mark.unstable
@pytest.mark.skipif(PLATFORM != "oci", reason="test is oci specific")
def test_single_stack(client: IntegrationInstance):
    """
    Test the behavior of cloud-init when interacting with the Oracle Cloud
    Infrastructure (OCI) Instance Metadata Service (IMDS) over IPv6, while
    selectively blocking IPv4 and IPv6 traffic.

    This test performs the following steps:
    1. Ensures the IPv6 IMDS is reachable via curl.
    2. Blocks IPv4 traffic and verifies that the IPv6 IMDS is still reachable.
    3. Blocks IPv6 traffic and verifies that the IPv6 IMDS is no longer
       reachable.
    4. Cleans up iptables rules to restore normal network behavior.

    The test is marked as unstable because it requires a specially configured
    instance that is running a private custom-made IPv6-only image that is not
    generally available. Thus, this test is only meant to be run manually by
    developers who have access to the necessary resources.
    """
    _install_netfilter_perstistent(client)

    # Ensure IPv6 is not disabled from a previous test
    client.execute(f"ip6tables -D OUTPUT -d {IPV6_METADATA_ADDRESS} -j REJECT")
    client.execute(f"ip6tables -D INPUT -s {IPV6_METADATA_ADDRESS} -j DROP")
    # Ensure IPv4 is not disabled from a previous test
    client.execute(f"iptables -D OUTPUT -d {IPV4_METADATA_ADDRESS} -j REJECT")
    client.execute(f"iptables -D INPUT -s {IPV4_METADATA_ADDRESS} -j DROP")

    # assert ipv6 imds is reachable via curl
    assert client.execute(
        "curl -f -g -6 -L http://[fd00:c1::a9fe:a9fe]/opc/v1/instance/"
    ).ok

    # Drop IPv4 responses
    assert client.execute(
        f"iptables -I INPUT -s {IPV4_METADATA_ADDRESS} -j DROP"
    ).ok
    # Block IPv4 requests
    assert client.execute(
        f"iptables -I OUTPUT -d {IPV4_METADATA_ADDRESS} -j REJECT"
    ).ok
    # Save the rules so they persist across reboot
    assert client.execute("sudo netfilter-persistent save").ok

    # assert ipv6 imds is reachable via curl when ipv4 is blocked
    assert client.execute(
        "curl -f -g -6 -L http://[fd00:c1::a9fe:a9fe]/opc/v1/instance/"
    ).ok

    _clean_and_wait_for_cloudinit(client)
    # cloud-init should be able to use ipv6 IMDS when ipv4 is blocked
    _test_reading_ipv6_metadata_succeeds(client)

    # Drop IPv6 responses
    assert client.execute(
        f"ip6tables -I INPUT -s {IPV6_METADATA_ADDRESS} -j DROP"
    ).ok
    # Block IPv6 requests
    assert client.execute(
        f"ip6tables -I OUTPUT -d {IPV6_METADATA_ADDRESS} -j REJECT"
    ).ok
    # Save the rules so they persist across reboot
    assert client.execute("sudo netfilter-persistent save").ok
    # assert that curling the ipv6 address fails when ipv6 is blocked
    assert not client.execute(
        "curl -f -g -6 -L http://[fd00:c1::a9fe:a9fe]/opc/v1/instance/"
    ).ok

    _clean_and_wait_for_cloudinit(client)
    # cloud-init should NOT be able to use ipv6 IMDS when ipv6 is blocked
    _test_reading_ipv6_metadata_fails(client)

    # Re-enable IPv6
    client.execute(f"ip6tables -D OUTPUT -d {IPV6_METADATA_ADDRESS} -j REJECT")
    client.execute(f"ip6tables -D INPUT -s {IPV6_METADATA_ADDRESS} -j DROP")
    # Re-enable IPv4
    client.execute(f"iptables -D OUTPUT -d {IPV4_METADATA_ADDRESS} -j REJECT")
    client.execute(f"iptables -D INPUT -s {IPV4_METADATA_ADDRESS} -j DROP")
