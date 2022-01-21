import json
import logging
import os

import pytest

from tests.integration_tests.clouds import ImageSpecification, IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.util import verify_clean_log

LOG = logging.getLogger("integration_testing.test_upgrade")

LOG_TEMPLATE = """\n\
=== `systemd-analyze` before:
{pre_systemd_analyze}
=== `systemd-analyze` after:
{post_systemd_analyze}

=== `systemd-analyze blame` before (first 10 lines):
{pre_systemd_blame}
=== `systemd-analyze blame` after (first 10 lines):
{post_systemd_blame}

=== `cloud-init analyze show` before:')
{pre_analyze_totals}
=== `cloud-init analyze show` after:')
{post_analyze_totals}

=== `cloud-init analyze blame` before (first 10 lines): ')
{pre_cloud_blame}
=== `cloud-init analyze blame` after (first 10 lines): ')
{post_cloud_blame}
"""

UNSUPPORTED_INSTALL_METHOD_MSG = (
    "Install method '{}' not supported for this test"
)
USER_DATA = """\
#cloud-config
hostname: SRU-worked
"""


def test_clean_boot_of_upgraded_package(session_cloud: IntegrationCloud):
    source = get_validated_source(session_cloud)
    if not source.installs_new_version():
        pytest.skip(UNSUPPORTED_INSTALL_METHOD_MSG.format(source))
        return  # type checking doesn't understand that skip raises
    if (
        ImageSpecification.from_os_image().release == "bionic"
        and session_cloud.settings.PLATFORM == "lxd_vm"
    ):
        # The issues that we see on Bionic VMs don't appear anywhere
        # else, including when calling KVM directly. It likely has to
        # do with the extra lxd-agent setup happening on bionic.
        # Given that we still have Bionic covered on all other platforms,
        # the risk of skipping bionic here seems low enough.
        pytest.skip("Upgrade test doesn't run on LXD VMs and bionic")
        return

    launch_kwargs = {
        "image_id": session_cloud.initial_image_id,
    }

    with session_cloud.launch(
        launch_kwargs=launch_kwargs,
        user_data=USER_DATA,
    ) as instance:
        # get pre values
        pre_hostname = instance.execute("hostname")
        pre_cloud_id = instance.execute("cloud-id")
        pre_result = instance.execute("cat /run/cloud-init/result.json")
        pre_network = instance.execute("cat /etc/netplan/50-cloud-init.yaml")
        pre_systemd_analyze = instance.execute("systemd-analyze")
        pre_systemd_blame = instance.execute("systemd-analyze blame")
        pre_cloud_analyze = instance.execute("cloud-init analyze show")
        pre_cloud_blame = instance.execute("cloud-init analyze blame")

        # Ensure no issues pre-upgrade
        log = instance.read_from_file("/var/log/cloud-init.log")
        assert not json.loads(pre_result)["v1"]["errors"]

        try:
            verify_clean_log(log)
        except AssertionError:
            LOG.warning(
                "There were errors/warnings/tracebacks pre-upgrade. "
                "Any failures may be due to pre-upgrade problem"
            )

        # Upgrade
        instance.install_new_cloud_init(source, take_snapshot=False)

        # 'cloud-init init' helps us understand if our pickling upgrade paths
        # have broken across re-constitution of a cached datasource. Some
        # platforms invalidate their datasource cache on reboot, so we run
        # it here to ensure we get a dirty run.
        assert instance.execute("cloud-init init").ok

        # Reboot
        instance.execute("hostname something-else")
        instance.restart()
        assert instance.execute("cloud-init status --wait --long").ok

        # get post values
        post_hostname = instance.execute("hostname")
        post_cloud_id = instance.execute("cloud-id")
        post_result = instance.execute("cat /run/cloud-init/result.json")
        post_network = instance.execute("cat /etc/netplan/50-cloud-init.yaml")
        post_systemd_analyze = instance.execute("systemd-analyze")
        post_systemd_blame = instance.execute("systemd-analyze blame")
        post_cloud_analyze = instance.execute("cloud-init analyze show")
        post_cloud_blame = instance.execute("cloud-init analyze blame")

        # Ensure no issues post-upgrade
        assert not json.loads(pre_result)["v1"]["errors"]

        log = instance.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)

        # Ensure important things stayed the same
        assert pre_hostname == post_hostname
        assert pre_cloud_id == post_cloud_id
        try:
            assert pre_result == post_result
        except AssertionError:
            if instance.settings.PLATFORM == "azure":
                pre_json = json.loads(pre_result)
                post_json = json.loads(post_result)
                assert pre_json["v1"]["datasource"].startswith(
                    "DataSourceAzure"
                )
                assert post_json["v1"]["datasource"].startswith(
                    "DataSourceAzure"
                )
        assert pre_network == post_network

        # Calculate and log all the boot numbers
        pre_analyze_totals = [
            x
            for x in pre_cloud_analyze.splitlines()
            if x.startswith("Finished stage") or x.startswith("Total Time")
        ]
        post_analyze_totals = [
            x
            for x in post_cloud_analyze.splitlines()
            if x.startswith("Finished stage") or x.startswith("Total Time")
        ]

        # pylint: disable=logging-format-interpolation
        LOG.info(
            LOG_TEMPLATE.format(
                pre_systemd_analyze=pre_systemd_analyze,
                post_systemd_analyze=post_systemd_analyze,
                pre_systemd_blame="\n".join(
                    pre_systemd_blame.splitlines()[:10]
                ),
                post_systemd_blame="\n".join(
                    post_systemd_blame.splitlines()[:10]
                ),
                pre_analyze_totals="\n".join(pre_analyze_totals),
                post_analyze_totals="\n".join(post_analyze_totals),
                pre_cloud_blame="\n".join(pre_cloud_blame.splitlines()[:10]),
                post_cloud_blame="\n".join(post_cloud_blame.splitlines()[:10]),
            )
        )


@pytest.mark.ci
@pytest.mark.ubuntu
def test_subsequent_boot_of_upgraded_package(session_cloud: IntegrationCloud):
    source = get_validated_source(session_cloud)
    if not source.installs_new_version():
        if os.environ.get("TRAVIS"):
            # If this isn't running on CI, we should know
            pytest.fail(UNSUPPORTED_INSTALL_METHOD_MSG.format(source))
        else:
            pytest.skip(UNSUPPORTED_INSTALL_METHOD_MSG.format(source))
        return  # type checking doesn't understand that skip raises

    launch_kwargs = {"image_id": session_cloud.initial_image_id}

    with session_cloud.launch(launch_kwargs=launch_kwargs) as instance:
        instance.install_new_cloud_init(
            source, take_snapshot=False, clean=False
        )
        instance.restart()
        assert instance.execute("cloud-init status --wait --long").ok
