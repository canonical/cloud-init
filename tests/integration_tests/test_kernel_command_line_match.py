import logging

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import (
    lxd_has_nocloud,
    override_kernel_command_line,
    wait_for_cloud_init,
)

log = logging.getLogger("integration_testing")


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
@pytest.mark.parametrize(
    "ds_str, configured, cmdline_configured",
    (
        (
            "ds=nocloud;s=http://my-url/;h=hostname",
            "DataSourceNoCloud [seed=None][dsmode=net]",
            True,
        ),
        ("ci.ds=openstack", "DataSourceOpenStack", True),
        ("bonding.max_bonds=0", "lxd_or_nocloud", False),
    ),
)
def test_lxd_datasource_kernel_override(
    ds_str, configured, cmdline_configured, client: IntegrationInstance
):
    """This test is twofold: it tests kernel command line override, which also
    validates OpenStack Ironic requirements. OpenStack Ironic does not
    advertise itself to cloud-init via any of the conventional methods: DMI,
    etc.

    On systemd, ds-identify is able to grok kernel command line, however to
    support cloud-init kernel command line parsing on non-systemd, parsing
    kernel command line in Python code is required.
    """

    if configured == "lxd_or_nocloud":
        configured = (
            "DataSourceNoCloud" if lxd_has_nocloud(client) else "DataSourceLXD"
        )
    override_kernel_command_line(ds_str, client)
    if cmdline_configured:
        assert (
            "Machine is configured by the kernel command line to run on single"
            f" datasource {configured}"
        ) in client.execute("cat /var/log/cloud-init.log")
    else:
        # verify that no plat
        log = client.execute("cat /var/log/cloud-init.log")
        assert (f"Detected platform: {configured}") in log
        assert (
            "Machine is configured by the kernel "
            "command line to run on single "
        ) not in log


GH_REPO_PATH = "https://raw.githubusercontent.com/canonical/cloud-init/main/"


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
@pytest.mark.parametrize(
    "ds_str",
    (f"ds=nocloud-net;s={GH_REPO_PATH}tests/data/kernel_cmdline_match/",),
)
def test_lxd_datasource_kernel_override_nocloud_net(
    ds_str, session_cloud: IntegrationCloud
):
    """NoCloud requirements vary slightly from other datasources with parsing
    nocloud-net due to historical reasons. Do to this variation, this is
    implemented in NoCloud's ds_detect and therefore has a different log
    message.
    """
    _ds_name, _, seed_url = ds_str.partition(";")
    _key, _, url_val = seed_url.partition("=")
    source = get_validated_source(session_cloud)
    with session_cloud.launch(
        wait=False,  # to prevent cloud-init status --wait
        launch_kwargs={
            # On Jammy and above, we detect the LXD datasource using a
            # socket available to the container. This prevents the socket
            # from being exposed in the container, so LXD will not be detected.
            # This allows us to wait for detection in 'init' stage with
            # DataSourceNoCloudNet.
            "config_dict": {"security.devlxd": False},
        },
    ) as client:
        # We know this will be an LXD instance due to our pytest mark
        client.instance.execute_via_ssh = False  # pyright: ignore
        assert wait_for_cloud_init(client, num_retries=60).ok
        if source.installs_new_version():
            client.install_new_cloud_init(source, clean=False)
        override_kernel_command_line(ds_str, client)

        logs = client.execute("cat /var/log/cloud-init.log")
        assert (
            "nocloud"
            == client.execute("cloud-init query platform").stdout.strip()
        )
        assert url_val in client.execute("cloud-init query subplatform").stdout
        assert (
            "Detected platform: DataSourceNoCloudNet [seed=None]"
            "[dsmode=net]. Checking for active instance data"
        ) in logs


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
def test_lxd_disable_cloud_init_cmdline(client: IntegrationInstance):
    """Verify cloud-init disablement via kernel command line works."""

    override_kernel_command_line("cloud-init=disabled", client)
    assert "Active: inactive (dead)" in client.execute(
        "systemctl status cloud-init"
    )


@pytest.mark.lxd_use_exec
def test_lxd_disable_cloud_init_file(client: IntegrationInstance):
    """Verify cloud-init disablement via file works."""

    client.execute("touch /etc/cloud/cloud-init.disabled")
    client.execute("cloud-init --clean")
    client.restart()
    assert "Active: inactive (dead)" in client.execute(
        "systemctl status cloud-init"
    )


@pytest.mark.lxd_use_exec
def test_lxd_disable_cloud_init_env(client: IntegrationInstance):
    """Verify cloud-init disablement via environment variable works."""
    env = """DefaultEnvironment=KERNEL_CMDLINE=cloud-init=disabled"""

    client.execute(f'echo "{env}" >> /etc/systemd/system.conf')

    client.execute("cloud-init --clean")
    client.restart()
    assert "Active: inactive (dead)" in client.execute(
        "systemctl status cloud-init"
    )
