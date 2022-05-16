import pytest

from tests.integration_tests.instances import IntegrationInstance

USER_DATA = """\
#cloud-config
runcmd:
 - echo "hi" >> /var/tmp/hi
"""


@pytest.mark.user_data(USER_DATA)
def test_frequency_override(client: IntegrationInstance):
    # Some pre-checks
    assert (
        "running config-scripts-user with frequency once-per-instance"
        in client.read_from_file("/var/log/cloud-init.log")
    )
    assert client.read_from_file("/var/tmp/hi").strip().count("hi") == 1

    # Change frequency of scripts-user to always
    config = client.read_from_file("/etc/cloud/cloud.cfg")
    new_config = config.replace("- scripts-user", "- [ scripts-user, always ]")
    client.write_to_file("/etc/cloud/cloud.cfg", new_config)

    client.restart()

    # Ensure the script was run again
    assert (
        "running config-scripts-user with frequency always"
        in client.read_from_file("/var/log/cloud-init.log")
    )
    assert client.read_from_file("/var/tmp/hi").strip().count("hi") == 2
