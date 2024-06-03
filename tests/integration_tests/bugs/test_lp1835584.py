"""Integration test for LP #1835584

Upstream linux kernels prior to 4.15 provide DMI product_uuid in uppercase.
More recent kernels switched to lowercase for DMI product_uuid. Azure
datasource uses this product_uuid as the instance-id for cloud-init.

The linux-azure-fips kernel installed in PRO FIPs images, that product UUID is
uppercase whereas the linux-azure cloud-optimized kernel reports the UUID as
lowercase.

In cases where product_uuid changes case, ensure cloud-init doesn't
recreate ssh hostkeys across reboot (due to detecting an instance_id change).

This currently only affects linux-azure-fips -> linux-azure on Bionic.

The test will launch a specific Bionic Ubuntu PRO FIPS image which has a
linux-azure-fips kernel known to report product_uuid as uppercase. Then upgrade
and reboot into linux-azure kernel which is known to report product_uuid as
lowercase.

Across the reboot, assert that we didn't re-run config_ssh by virtue of
seeing only one semaphore creation log entry of type:

 Writing to /var/lib/cloud/instances/<UUID>/sem/config_ssh -

https://bugs.launchpad.net/cloud-init/+bug/1835584
"""
import re

import pytest
from pycloudlib.cloud import ImageType

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE


def _check_iid_insensitive_across_kernel_upgrade(
    instance: IntegrationInstance,
):
    uuid = instance.read_from_file("/sys/class/dmi/id/product_uuid")
    assert (
        uuid.isupper()
    ), "Expected uppercase UUID on Ubuntu FIPS image {}".format(uuid)
    orig_kernel = instance.execute("uname -r").strip()
    assert "azure-fips" in orig_kernel
    result = instance.execute("apt-get update")
    # Install a 5.4+ kernel which provides lowercase product_uuid
    result = instance.execute("apt-get install linux-azure --assume-yes")
    if not result.ok:
        pytest.fail("Unable to install linux-azure kernel: {}".format(result))
    # Remove ubuntu-azure-fips metapkg which mandates FIPS-flavour kernel
    result = instance.execute("ua disable fips --assume-yes")
    assert result.ok, "Unable to disable fips: {}".format(result)
    instance.restart()
    new_kernel = instance.execute("uname -r").strip()
    assert orig_kernel != new_kernel
    assert "azure-fips" not in new_kernel
    assert "azure" in new_kernel
    new_uuid = instance.read_from_file("/sys/class/dmi/id/product_uuid")
    assert (
        uuid.lower() == new_uuid
    ), "Expected UUID on linux-azure to be lowercase of FIPS: {}".format(uuid)
    log = instance.read_from_file("/var/log/cloud-init.log")
    RE_CONFIG_SSH_SEMAPHORE = r"Writing.*sem/config_ssh "
    ssh_runs = len(re.findall(RE_CONFIG_SSH_SEMAPHORE, log))
    assert 1 == ssh_runs, "config_ssh ran too many times {}".format(ssh_runs)


@pytest.mark.skipif(PLATFORM != "azure", reason="Test is Azure specific")
@pytest.mark.integration_cloud_args(image_type=ImageType.PRO_FIPS)
def test_azure_kernel_upgrade_case_insensitive_uuid(
    session_cloud: IntegrationCloud,
):
    if (CURRENT_RELEASE.os, CURRENT_RELEASE.series) != ("ubuntu", "bionic"):
        pytest.skip(
            f"Test only supports ubuntu:bionic not {CURRENT_RELEASE.os}: "
            f"{CURRENT_RELEASE.series}"
        )
    source = get_validated_source(session_cloud)
    if not source.installs_new_version():
        pytest.skip(
            "Provide CLOUD_INIT_SOURCE to install expected working cloud-init"
        )
    with session_cloud.launch(
        launch_kwargs={
            "image_id": session_cloud.cloud_instance.daily_image(
                CURRENT_RELEASE.series, image_type=ImageType.PRO_FIPS
            )
        }
    ) as instance:
        # We can't use setup_image fixture here because we want to avoid
        # taking a snapshot or cleaning the booted machine after cloud-init
        # upgrade.
        instance.install_new_cloud_init(source, clean=False)
        _check_iid_insensitive_across_kernel_upgrade(instance)
