import uuid
from typing import cast

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL

_INSTANCE_ID = uuid.uuid4()


def setup_meta_data(instance: LXDInstance):
    """Increment the instance id and apply it to the instance."""
    global _INSTANCE_ID
    _INSTANCE_ID = uuid.UUID(int=(1 + _INSTANCE_ID.int))
    command = [
        "lxc",
        "config",
        "set",
        instance.name,
        f"volatile.cloud-init.instance-id={_INSTANCE_ID}",
    ]
    assert subp.subp(command)


# class TestInstanceID:
@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"] or CURRENT_RELEASE == FOCAL,
    reason="Uses lxd-specific behavior.",
)
@pytest.mark.lxd_setup.with_args(setup_meta_data)
@pytest.mark.lxd_use_exec
def test_instance_id_changes(client: IntegrationInstance):
    """Verify instance id change behavior

    If the id from the datasource changes, cloud-init should update the
    instance id link.
    """
    client.execute("cloud-init status --wait")
    # check that instance id is the one we set
    assert (
        str(_INSTANCE_ID)
        == client.execute("cloud-init query instance-id").stdout.rstrip()
    )
    assert (
        f"/var/lib/cloud/instances/{_INSTANCE_ID}"
        == client.execute(
            "readlink -f /var/lib/cloud/instance"
        ).stdout.rstrip()
    )

    instance = cast(LXDInstance, client.instance)
    setup_meta_data(instance)
    client.restart()
    client.execute("cloud-init status --wait")
    # check that instance id is the one we reset
    assert (
        str(_INSTANCE_ID)
        == client.execute("cloud-init query instance-id").stdout.rstrip()
    )
    assert (
        f"/var/lib/cloud/instances/{_INSTANCE_ID}"
        == client.execute(
            "readlink -f /var/lib/cloud/instance"
        ).stdout.rstrip()
    )


@pytest.mark.lxd_use_exec
def test_instance_id_no_changes(client: IntegrationInstance):
    """Verify instance id no change behavior

    If the id from the datasource does not change, cloud-init should not
    update the instance id link.
    """
    instance_id = client.execute(
        "cloud-init query instance-id"
    ).stdout.rstrip()
    assert (
        f"/var/lib/cloud/instances/{instance_id}"
        == client.execute(
            "readlink -f /var/lib/cloud/instance"
        ).stdout.rstrip()
    )
    client.restart()
    client.execute("cloud-init status --wait")
    assert (
        instance_id
        == client.execute("cloud-init query instance-id").stdout.rstrip()
    )
    assert (
        f"/var/lib/cloud/instances/{instance_id}"
        == client.execute(
            "readlink -f /var/lib/cloud/instance"
        ).stdout.rstrip()
    )
