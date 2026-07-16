import logging
import time
from collections import namedtuple

import paramiko
import pytest
import yaml
from pycloudlib.ec2.instance import EC2Instance

from cloudinit.subp import subp
from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import (
    CURRENT_RELEASE,
    FOCAL,
    UBUNTU_STABLE,
)
from tests.integration_tests.util import (
    push_and_enable_systemd_unit,
    verify_clean_boot,
    verify_clean_log,
    wait_for_cloud_init,
)

USER_DATA = """\
#cloud-config
updates:
  network:
    when: ['hotplug']
"""

USER_DATA_HOTPLUG_DISABLED = """\
#cloud-config
updates:
  network:
    when: ['boot-new-instance']
"""

LOG = logging.getLogger()
ip_addr = namedtuple("ip_addr", "interface state ip4 ip6")


def _wait_till_hotplug_complete(client, expected_runs=1):
    for _ in range(60):
        if client.execute("command -v systemctl").ok:
            if "failed" == client.execute(
                "systemctl is-active cloud-init-hotplugd.service"
            ):
                r = client.execute(
                    "systemctl status cloud-init-hotplugd.service"
                )
                if not r.ok:
                    raise AssertionError(
                        "cloud-init-hotplugd.service failed: {r.stdout}"
                    )

        log = client.read_from_file("/var/log/cloud-init.log")
        if log.count("Exiting hotplug handler") == expected_runs:
            return log
        time.sleep(1)
    raise Exception("Waiting for hotplug handler failed")


def _get_ip_addr(client, *, _retries: int = 0):
    ips = []
    lines = client.execute("ip --brief addr").split("\n")
    for line in lines:
        attributes = line.split()
        interface, state = attributes[0], attributes[1]
        ip4_cidr = attributes[2] if len(attributes) > 2 else None

        # Retry to wait for ipv6_cidr:
        # ens6 UP <ipv4_cidr> metric 200 <ipv6_cidr> <ipv6_cidr scope link>
        if len(attributes) == 6 and _retries < 3:
            time.sleep(1)
            return _get_ip_addr(client, _retries=_retries + 1)

        # The output of `ip --brief addr` can contain metric info:
        # ens5 UP <ipv4_cidr> metric 100 <ipv6_cidr> ...
        ip6_cidr = None
        if len(attributes) > 3:
            if attributes[3] != "metric":
                ip6_cidr = attributes[3]
            elif len(attributes) > 5:
                ip6_cidr = attributes[5]
        ip4 = ip4_cidr.split("/")[0] if ip4_cidr else None
        ip6 = ip6_cidr.split("/")[0] if ip6_cidr else None
        ip = ip_addr(interface, state, ip4, ip6)
        ips.append(ip)
    return ips


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        "Test was written for openstack but can likely run on other platforms."
    ),
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL,
    reason="Openstack network metadata support was added in focal.",
)
@pytest.mark.user_data(USER_DATA)
def test_hotplug_add(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).ok

    # Add new NIC
    added_ip = client.instance.add_network_interface()
    _wait_till_hotplug_complete(client, expected_runs=1)
    ips_after_add = _get_ip_addr(client)
    new_addition = [ip for ip in ips_after_add if ip.ip4 == added_ip][0]

    assert len(ips_after_add) == len(ips_before) + 1
    assert added_ip not in [ip.ip4 for ip in ips_before]
    assert added_ip in [ip.ip4 for ip in ips_after_add]
    assert new_addition.state == "UP"

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface in config["network"]["ethernets"]

    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )


@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm", "ec2", "openstack", "azure"],
    reason=(f"HOTPLUG is not supported in {PLATFORM}."),
)
def _test_hotplug_enabled_by_cmd(client: IntegrationInstance):
    assert "disabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )
    ret = client.execute("cloud-init devel hotplug-hook -s net enable")
    assert ret.ok, ret.stderr
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "hotplug-hook called with the following arguments: "
        "{hotplug_action: enable" in log
    )

    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )
    log = client.read_from_file("/var/log/cloud-init.log")
    assert (
        "hotplug-hook called with the following arguments: "
        "{hotplug_action: query" in log
    )
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).ok


@pytest.mark.user_data(USER_DATA_HOTPLUG_DISABLED)
def test_hotplug_enable_cmd(client: IntegrationInstance):
    _test_hotplug_enabled_by_cmd(client)


@pytest.mark.skipif(
    PLATFORM != "ec2",
    reason=(
        f"Test was written for {PLATFORM} but can likely run on "
        "other platforms."
    ),
)
@pytest.mark.user_data(USER_DATA_HOTPLUG_DISABLED)
def test_hotplug_enable_cmd_ec2(client: IntegrationInstance):
    _test_hotplug_enabled_by_cmd(client)
    ips_before = _get_ip_addr(client)

    # Add new NIC
    added_ip = client.instance.add_network_interface()
    _wait_till_hotplug_complete(client, expected_runs=4)
    ips_after_add = _get_ip_addr(client)
    new_addition = [ip for ip in ips_after_add if ip.ip4 == added_ip][0]

    assert len(ips_after_add) == len(ips_before) + 1
    assert added_ip not in [ip.ip4 for ip in ips_before]
    assert added_ip in [ip.ip4 for ip in ips_after_add]
    assert new_addition.state == "UP"

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    assert new_addition.interface in config["network"]["ethernets"]


@pytest.mark.skipif(
    PLATFORM != "openstack",
    reason=(
        "Test was written for openstack but can likely run on other platforms."
    ),
)
def test_no_hotplug_in_userdata(client: IntegrationInstance):
    ips_before = _get_ip_addr(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert client.execute(
        "test -f /etc/udev/rules.d/90-cloud-init-hook-hotplug.rules"
    ).failed

    # Add new NIC
    client.instance.add_network_interface()
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "hotplug-hook" not in log

    ips_after_add = _get_ip_addr(client)
    if len(ips_after_add) == len(ips_before) + 1:
        # We can see the device, but it should not have been brought up
        new_ip = [ip for ip in ips_after_add if ip not in ips_before][0]
        assert new_ip.state == "DOWN"
    else:
        assert len(ips_after_add) == len(ips_before)

    assert "disabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
@pytest.mark.user_data(USER_DATA)
def test_multi_nic_hotplug(client: IntegrationInstance):
    """Tests that additional secondary NICs are routable from non-local
    networks after the hotplug hook is executed when network updates
    are configured on the HOTPLUG event."""
    ips_before = _get_ip_addr(client)
    secondary_priv_ip = client.instance.add_network_interface(
        ipv4_public_ip_count=1,
    )
    _wait_till_hotplug_complete(client, expected_runs=1)

    log_content = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log_content)
    verify_clean_boot(client)

    ips_after_add = _get_ip_addr(client)

    netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    config = yaml.safe_load(netplan_cfg)
    new_addition = [ip for ip in ips_after_add if ip.ip4 == secondary_priv_ip][
        0
    ]
    assert new_addition.interface in config["network"]["ethernets"]
    new_nic_cfg = config["network"]["ethernets"][new_addition.interface]
    assert [{"from": secondary_priv_ip, "table": 101}] == new_nic_cfg[
        "routing-policy"
    ]

    assert len(ips_after_add) == len(ips_before) + 1

    # help mypy realize client.instance is an instance of EC2Instance as
    # public_ips is only available on ec2 instances
    assert isinstance(client.instance, EC2Instance)
    public_ips = client.instance.public_ips
    assert len(public_ips) == 2

    # SSH over all public ips works
    for pub_ip in public_ips:
        subp("nc -w 10 -zv " + pub_ip + " 22", shell=True)

    log_content = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log_content)
    verify_clean_boot(client)


# TODO: support early hotplug
#
# This test usually passes without the `wait_for_cloud_init()`
# but sometimes the hotplug event races with the end of cloud-init
# so occasionally fails. For now, document this shortcoming and
# wait for cloud-init to complete before testing the behavior.
@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
def test_multi_nic_hotplug_vpc(session_cloud: IntegrationCloud):
    """Tests that additional secondary NICs are routable from local
    networks after the hotplug hook is executed when network updates
    are configured on the HOTPLUG event."""
    with session_cloud.launch(
        user_data=USER_DATA
    ) as client, session_cloud.launch() as bastion:
        ips_before = _get_ip_addr(client)
        primary_priv_ip4 = ips_before[1].ip4
        primary_priv_ip6 = ips_before[1].ip6
        # cloud-init is incapable of hotplugged devices until after
        # completion (cloud-init.target / cloud-init status --wait)
        #
        # To reliably test cloud-init hotplug, wait for completion before
        # testing behaviors.
        wait_for_cloud_init(client)
        client.instance.add_network_interface(ipv6_address_count=1)

        _wait_till_hotplug_complete(client)
        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)
        verify_clean_boot(client)

        netplan_cfg = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
        config = yaml.safe_load(netplan_cfg)

        ips_after_add = _get_ip_addr(client)
        secondary_priv_ip4 = ips_after_add[2].ip4
        secondary_priv_ip6 = ips_after_add[2].ip6
        assert primary_priv_ip4 != secondary_priv_ip4

        new_addition = [
            ip for ip in ips_after_add if ip.ip4 == secondary_priv_ip4
        ][0]
        assert new_addition.interface in config["network"]["ethernets"]
        new_nic_cfg = config["network"]["ethernets"][new_addition.interface]
        assert "routing-policy" in new_nic_cfg
        assert [
            {"from": secondary_priv_ip4, "table": 101},
            {"from": secondary_priv_ip6, "table": 101},
        ] == new_nic_cfg["routing-policy"]

        assert len(ips_after_add) == len(ips_before) + 1

        # pings to primary and secondary NICs work
        # use -w so that test is less flaky with temporary network failure
        r = bastion.execute(f"ping -c1 -w5 {primary_priv_ip4}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 -w5 {secondary_priv_ip4}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 -w5 {primary_priv_ip6}")
        assert r.ok, r.stdout
        r = bastion.execute(f"ping -c1 -w5 {secondary_priv_ip6}")
        assert r.ok, r.stdout

        # Check every route has metrics associated. See LP: #2055397
        ip_route_show = client.execute("ip route show")
        assert ip_route_show.ok, ip_route_show.stderr
        for route in ip_route_show.splitlines():
            assert "metric" in route, "Expected metric to be in the route"

        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)
        verify_clean_boot(client)


@pytest.mark.skipif(PLATFORM != "ec2", reason="test is ec2 specific")
@pytest.mark.skipif(
    CURRENT_RELEASE not in UBUNTU_STABLE,
    reason="Docker repo does not contain pkgs for non stable releases.",
)
@pytest.mark.user_data(USER_DATA)
def test_no_hotplug_triggered_by_docker(client: IntegrationInstance):
    # Install docker
    r = client.execute("curl -fsSL https://get.docker.com | sh")
    assert r.ok, r.stderr

    # Start and stop a container
    r = client.execute("docker run -dit --name ff ubuntu:focal")
    assert r.ok, r.stderr
    r = client.execute("docker stop ff")
    assert r.ok, r.stderr

    # Verify hotplug-hook was not called
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Exiting hotplug handler" not in log
    assert "hotplug-hook" not in log

    # Verify hotplug was enabled
    assert "enabled" == client.execute(
        "cloud-init devel hotplug-hook -s net query"
    )


def wait_for_cmd(
    client: IntegrationInstance, cmd: str, return_code: int
) -> None:
    for _ in range(60):
        try:
            res = client.execute(cmd)
        except paramiko.ssh_exception.SSHException:
            pass
        else:
            if res.return_code == return_code:
                return
        time.sleep(1)
    assert False, f"`{cmd}` never exited with {return_code}"


def assert_systemctl_status_code(
    client: IntegrationInstance, service: str, return_code: int
):
    result = client.execute(f"systemctl status {service}")
    assert result.return_code == return_code, (
        f"status of {service} expected to be {return_code} but was"
        f" {result.return_code}\nstdout: {result.stdout}\n"
        f"stderr {result.stderr}"
    )


BLOCK_CLOUD_CONFIG = """\
[Unit]
Description=Block cloud-config.service
After=cloud-config.target
Before=cloud-config.service

DefaultDependencies=no
Before=shutdown.target
Conflicts=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/sleep 360
TimeoutSec=0

# Output needs to appear in instance console output
StandardOutput=journal+console

[Install]
WantedBy=cloud-config.service
"""  # noqa: E501


BLOCK_CLOUD_FINAL = """\
[Unit]
Description=Block cloud-final.service
After=cloud-config.target
Before=cloud-final.service

DefaultDependencies=no
Before=shutdown.target
Conflicts=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/sleep 360
TimeoutSec=0

# Output needs to appear in instance console output
StandardOutput=journal+console

[Install]
WantedBy=cloud-final.service
"""  # noqa: E501


def _customize_environment(client: IntegrationInstance):
    push_and_enable_systemd_unit(
        client, "block-cloud-config.service", BLOCK_CLOUD_CONFIG
    )
    push_and_enable_systemd_unit(
        client, "block-cloud-final.service", BLOCK_CLOUD_FINAL
    )

    # Disable pam_nologin for 1000(ubuntu) user to allow ssh access early
    # during boot. Without this we get:
    #
    # System is booting up. Unprivileged users are not permitted to log in yet.
    # Please come back later. For technical details, see pam_nologin(8).
    #
    # sshd[xxx]: fatal: Access denied for user ubuntu by PAM account
    # configuration [preauth]
    #
    # See: pam(7), pam_nologin(8), pam_succeed_id(8)
    contents = client.read_from_file("/etc/pam.d/sshd")
    contents = (
        "account [success=1 default=ignore] pam_succeed_if.so quiet uid eq"
        " 1000\n\n" + contents
    )
    client.write_to_file("/etc/pam.d/sshd", contents)

    client.instance.shutdown(wait=True)
    client.instance.start(wait=False)


@pytest.mark.skipif(
    PLATFORM != "ec2",
    reason="test is ec2 specific but should work on other platforms with the"
    " ability to add_network_interface",
)
@pytest.mark.user_data(USER_DATA)
def test_nics_before_config_trigger_hotplug(client: IntegrationInstance):
    """
    Test that NICs added after the Network boot stage but before
    the rest boot stages do trigger cloud-init-hotplugd.

    Note: Do not test first boot, as cc_install_hotplug runs at
    config-final.service time.
    """
    _customize_environment(client)

    # wait until we are between cloud-config.target done and
    # cloud-config.service
    wait_for_cmd(client, "systemctl status cloud-config.target", 0)
    wait_for_cmd(client, "systemctl status block-cloud-config.service", 3)

    # socket active but service not
    assert_systemctl_status_code(client, "cloud-init-hotplugd.socket", 0)
    assert_systemctl_status_code(client, "cloud-init-hotplugd.service", 3)

    assert_systemctl_status_code(client, "cloud-config.service", 3)
    assert_systemctl_status_code(client, "cloud-final.service", 3)

    client.instance.add_network_interface()

    assert_systemctl_status_code(client, "cloud-config.service", 3)
    assert_systemctl_status_code(client, "cloud-final.service", 3)

    # unblock cloud-config.service
    assert client.execute("systemctl stop block-cloud-config.service").ok
    wait_for_cmd(client, "systemctl status cloud-config.service", 0)
    wait_for_cmd(client, "systemctl status block-cloud-final.service", 3)
    assert_systemctl_status_code(client, "cloud-final.service", 3)

    # hotplug didn't run before cloud-final.service
    _wait_till_hotplug_complete(client, expected_runs=0)

    # unblock cloud-final.service
    assert client.execute("systemctl stop block-cloud-final.service").ok

    wait_for_cloud_init(client)
    _wait_till_hotplug_complete(client, expected_runs=1)
