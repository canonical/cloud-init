"""Integration test for gh-671.

Verify that on Azure that if a default user and password are specified
through the Azure API that a change in the default password overwrites
the old password
"""

import crypt

import pytest

from tests.integration_tests.clouds import IntegrationCloud

OLD_PASSWORD = "DoIM33tTheComplexityRequirements!??"
NEW_PASSWORD = "DoIM33tTheComplexityRequirementsNow!??"


def _check_password(instance, unhashed_password):
    shadow_password = instance.execute("getent shadow ubuntu").split(":")[1]
    salt = shadow_password.rsplit("$", 1)[0]
    hashed_password = crypt.crypt(unhashed_password, salt)
    assert shadow_password == hashed_password


@pytest.mark.azure
def test_update_default_password(setup_image, session_cloud: IntegrationCloud):
    os_profile = {
        "os_profile": {
            "admin_password": "",
            "linux_configuration": {"disable_password_authentication": False},
        }
    }
    os_profile["os_profile"]["admin_password"] = OLD_PASSWORD
    instance1 = session_cloud.launch(launch_kwargs={"vm_params": os_profile})

    _check_password(instance1, OLD_PASSWORD)

    snapshot_id = instance1.cloud.cloud_instance.snapshot(
        instance1.instance, delete_provisioned_user=False
    )

    os_profile["os_profile"]["admin_password"] = NEW_PASSWORD
    try:
        with session_cloud.launch(
            launch_kwargs={
                "image_id": snapshot_id,
                "vm_params": os_profile,
            }
        ) as instance2:
            _check_password(instance2, NEW_PASSWORD)
    finally:
        session_cloud.cloud_instance.delete_image(snapshot_id)
        instance1.destroy()
