import re
from typing import Set

import oci
import pytest
import yaml
from pycloudlib.oci.utils import wait_till_ready

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

DS_CFG = """\
#cloud-config
datasource:
  Oracle:
    configure_secondary_nics: True
"""


def _customize_environment(client: IntegrationInstance, iscsi: bool = True):
    assert client.execute("rm -f /run/initramfs/open-iscsi.interface").ok
    if not iscsi:
        assert client.execute("rm -f /run/net-*.conf").ok

    # Force network config
    assert client.execute(
        "rm -f /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
    ).ok
    client.execute("cloud-init clean --logs")
    client.restart()


def extract_interface_names(network_config: dict) -> Set[str]:
    if network_config["version"] == 1:
        interfaces = map(lambda conf: conf["name"], network_config["config"])
    elif network_config["version"] == 2:
        interfaces = network_config["ethernets"].keys()
    else:
        raise NotImplementedError(
            f'Implement me for version={network_config["version"]}'
        )
    return set(interfaces)


@pytest.mark.oci
def test_oci_networking_iscsi_instance(client: IntegrationInstance):
    _customize_environment(client, iscsi=True)
    result_net_files = client.execute("ls /run/net-*.conf")
    assert result_net_files.ok, "No net files found under /run"

    log = client.read_from_file("/var/log/cloud-init.log")
    with open("oci.log", "w") as f:
        f.write(log)
    verify_clean_log(log)

    assert (
        "opc/v2/vnics/" not in log
    ), "vnic data was fetched and it should no have been"

    netplan_yaml = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    netplan_cfg = yaml.safe_load(netplan_yaml)
    configured_interfaces = extract_interface_names(netplan_cfg["network"])

    expeceted_interfaces = set(
        re.findall(r"/run/net-(.+)\.conf", result_net_files.stdout)
    )
    for expected_interface in expeceted_interfaces:
        assert (
            f"Reading from /run/net-{expected_interface}.conf" in log
        ), "Expected {expected_interface} not found in: {log}"

    not_found_interfaces = expeceted_interfaces.difference(
        configured_interfaces
    )
    assert not not_found_interfaces, (
        f"Interfaces, {not_found_interfaces}, expected to be configured in"
        f" {netplan_cfg['network']}"
    )


@pytest.fixture(scope="function")
def client_with_secondary_vnic(session_cloud: IntegrationCloud):
    """Attach a temporary vnic to the created instance

    Note: It assumes the associated compartment has at least one subnet and
    creates the vnic in the first encountered subnet.
    """
    with session_cloud.launch(launch_kwargs={}) as client:
        compute_client = session_cloud.cloud_instance.compute_client

        subnet_id = (
            client.instance.network_client.list_subnets(
                client.instance.compartment_id, limit=1
            )
            .data[0]
            .id
        )
        create_vnic_details = oci.core.models.CreateVnicDetails(
            assign_private_dns_record=False,
            assign_public_ip=False,
            subnet_id=subnet_id,
        )
        attach_vnic_details = oci.core.models.AttachVnicDetails(
            create_vnic_details=create_vnic_details,
            instance_id=client.instance.instance_id,
        )
        vnic_data = compute_client.attach_vnic(attach_vnic_details).data

        wait_till_ready(
            func=compute_client.get_vnic_attachment,
            current_data=vnic_data,
            desired_state=vnic_data.LIFECYCLE_STATE_ATTACHED,
        )
        yield client
        response = compute_client.detach_vnic(vnic_data.id)
        assert (
            response.status == 204
        ), f"Attached vnic not deleted: {vnic_data.id}"


@pytest.mark.oci
def test_oci_networking_iscsi_instance_secondary_vnics(
    client_with_secondary_vnic, tmpdir
):
    client = client_with_secondary_vnic

    cfg = tmpdir.join("01_oracle_datasource.cfg")
    with open(cfg, "w") as f:
        f.write(DS_CFG)
    client.push_file(cfg, "/etc/cloud/cloud.cfg.d/01_oracle_datasource.cfg")
    _customize_environment(client, iscsi=True)

    log = client.read_from_file("/var/log/cloud-init.log")
    with open("oci.log", "w") as f:
        f.write(log)
    verify_clean_log(log)

    assert "opc/v2/vnics/" in log, f"vnics data not fetched in {log}"
    netplan_yaml = client.read_from_file("/etc/netplan/50-cloud-init.yaml")
    netplan_cfg = yaml.safe_load(netplan_yaml)
    configured_interfaces = extract_interface_names(netplan_cfg["network"])
    assert 2 == len(configured_interfaces)


@pytest.mark.skip(
    reason="Figure out how to configure a non iscsi network instance in oci"
)
@pytest.mark.oci
def test_oci_networking_non_iscsi_instance(session_cloud: IntegrationCloud):
    launch_options = oci.core.models.LaunchOptions(
        boot_volume_type=oci.core.models.LaunchOptions.BOOT_VOLUME_TYPE_VFIO,
        network_type=oci.core.models.LaunchOptions.NETWORK_TYPE_VFIO,
    )
    with session_cloud.launch(
        launch_kwargs={"launch_options": launch_options}
    ) as client:
        _customize_environment(client, iscsi=False)
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert "opc/v2/vnics/" in log, f"vnics data not fetched in {log}"
