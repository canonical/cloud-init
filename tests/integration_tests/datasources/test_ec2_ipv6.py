import re

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM


def _test_crawl(client, ip):
    assert client.execute("cloud-init clean --logs").ok
    assert client.execute("cloud-init init --local").ok
    log = client.read_from_file("/var/log/cloud-init.log")
    assert f"Using metadata source: '{ip}'" in log
    result = re.findall(r"Getting metadata took (\d+.\d+) seconds", log)
    if len(result) != 1:
        pytest.fail(f"Expected 1 metadata crawl time, got {result}")
    # 20 would still be a crazy long time for metadata service to crawl,
    # but it's short enough to know we're not waiting for a response
    assert float(result[0]) < 20


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_dual_stack(client: IntegrationInstance):
    # Drop IPv4 responses
    assert client.execute("iptables -I INPUT -s 169.254.169.254 -j DROP").ok
    _test_crawl(client, "http://[fd00:ec2::254]")

    # Block IPv4 requests
    assert client.execute("iptables -I OUTPUT -d 169.254.169.254 -j REJECT").ok
    _test_crawl(client, "http://[fd00:ec2::254]")

    # Re-enable IPv4
    assert client.execute("iptables -D OUTPUT -d 169.254.169.254 -j REJECT").ok
    assert client.execute("iptables -D INPUT -s 169.254.169.254 -j DROP").ok

    # Drop IPv6 responses
    assert client.execute("ip6tables -I INPUT -s fd00:ec2::254 -j DROP").ok
    _test_crawl(client, "http://169.254.169.254")

    # Block IPv6 requests
    assert client.execute("ip6tables -I OUTPUT -d fd00:ec2::254 -j REJECT").ok
    _test_crawl(client, "http://169.254.169.254")

    # Force NoDHCPLeaseError (by removing dhcp clients) and assert ipv6 still
    # works
    # Destructive test goes last
    # dhclient is at /sbin/dhclient on bionic but /usr/sbin/dhclient elseware
    for dhcp_client in ("dhclient", "dhcpcd"):
        if client.execute(f"command -v {dhcp_client}").ok:
            assert client.execute(f"rm $(command -v {dhcp_client})").ok

    client.restart()
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Crawled metadata service using link-local ipv6" in log
