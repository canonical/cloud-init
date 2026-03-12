import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, JAMMY

USER_DATA = """\
#cloud-config
runcmd:
 - echo "hi" >> /var/tmp/hi
snap:
 commands:
   00: echo heya
"""


@pytest.mark.user_data(USER_DATA)
def test_frequency_override(client: IntegrationInstance):
    # Some pre-checks
    assert (
        "running config-scripts_user with frequency once-per-instance"
        in client.read_from_file("/var/log/cloud-init.log")
    )
    assert client.read_from_file("/var/tmp/hi").strip().count("hi") == 1
    # This workaround is not needed for OCI, so just skip it
    if CURRENT_RELEASE.os == "ubuntu" and PLATFORM != "oci":
        if CURRENT_RELEASE > JAMMY:
            # Newer series will not block on snapd.seeded.service
            assert "snapd.seeded.service" not in client.execute(
                "systemctl show -P After cloud-config.service"
            )
            assert client.execute(
                "test -f /var/lib/cloud/sem/snap_seeded.once"
            ).ok
        else:
            # Jammy series and earlier will block on snapd.seeded.service
            assert "snapd.seeded.service" in client.execute(
                "systemctl show -P After cloud-config.service"
            )
            # Jammy will not create a snap-seeded semaphore.
            assert not client.execute(
                "test -f /var/lib/cloud/sem/snap_seeded.once"
            ).ok

    # Change frequency of scripts_user to always
    config = client.read_from_file("/etc/cloud/cloud.cfg")
    new_config = config.replace("- scripts_user", "- [ scripts_user, always ]")
    client.write_to_file("/etc/cloud/cloud.cfg", new_config)

    client.restart()

    # Ensure the script was run again
    assert (
        "running config-scripts_user with frequency always"
        in client.read_from_file("/var/log/cloud-init.log")
    )
    assert client.read_from_file("/var/tmp/hi").strip().count("hi") == 2
