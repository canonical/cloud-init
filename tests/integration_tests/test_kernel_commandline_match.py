import logging

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.conftest import get_validated_source
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import wait_for_cloud_init

log = logging.getLogger("integration_testing")


def override_kernel_cmdline(ds_str: str, c: IntegrationInstance) -> str:
    """
    Configure grub's kernel command line to tell cloud-init to use OpenStack
    - even though LXD should naturally be detected.

    This runs on LXD, but forces cloud-init to attempt to run OpenStack.
    This will inevitably fail on LXD, but we only care that it tried - on
    Ironic, for example, it will succeed.
    """
    client = c

    # The final output in /etc/default/grub should be:
    #
    # GRUB_CMDLINE_LINUX="'ds=nocloud;s=http://my-url/'"
    #
    # That ensures that the kernel commandline passed into
    # /boot/efi/EFI/ubuntu/grub.cfg will be properly single-quoted
    #
    # Example:
    #
    # linux /boot/vmlinuz-5.15.0-1030-kvm ro 'ds=nocloud;s=http://my-url/'
    #
    # Not doing this will result in a semicolon-delimited ds argument
    # terminating the kernel arguments prematurely.
    client.execute('printf "GRUB_CMDLINE_LINUX=\\"" >> /etc/default/grub')
    client.execute('printf "\'" >> /etc/default/grub')
    client.execute(f"printf '{ds_str}' >> /etc/default/grub")
    client.execute('printf "\'\\"" >> /etc/default/grub')

    # We should probably include non-systemd distros at some point. This should
    # most likely be as simple as updating the output path for grub-mkconfig
    client.execute("grub-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg")
    client.execute("cloud-init clean --logs")
    client.instance.shutdown(wait=False)
    try:
        client.instance.wait_for_state("STOPPED", num_retries=20)
    except RuntimeError as e:
        log.warning(
            "Retrying shutdown due to timeout on initial shutdown request %s",
            str(e),
        )
        client.instance.shutdown()

    client.instance.execute_via_ssh = False
    client.instance.start()
    client.execute("cloud-init status --wait")
    return client.execute("cat /var/log/cloud-init.log")


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
@pytest.mark.parametrize(
    "ds_str, configured",
    (
        (
            "ds=nocloud;s=http://my-url/;h=hostname",
            "DataSourceNoCloud [seed=None][dsmode=net]",
        ),
        ("ci.ds=openstack", "DataSourceOpenStack"),
    ),
)
def test_lxd_datasource_kernel_override(
    ds_str, configured, client: IntegrationInstance
):
    """This test is twofold: it tests kernel commandline override, which also
    validates OpenStack Ironic requirements. OpenStack Ironic does not
    advertise itself to cloud-init via any of the conventional methods: DMI,
    etc.

    On systemd, ds-identify is able to grok kernel commandline, however to
    support cloud-init kernel command line parsing on non-systemd, parsing
    kernel commandline in Python code is required.
    """

    assert (
        "Machine is configured by the kernel commandline to run on single "
        f"datasource {configured}"
    ) in override_kernel_cmdline(ds_str, client)


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
        launch_kwargs={
            # On Jammy and above, we detect the LXD datasource using a
            # socket available to the container. This prevents the socket
            # from being exposed in the container, so LXD will not be detected.
            # This allows us to wait for detection in 'init' stage with
            # DataSourceNoCloudNet.
            "config_dict": {"security.devlxd": False},
            "wait": False,  # to prevent cloud-init status --wait
        }
    ) as client:
        # We know this will be an LXD instance due to our pytest mark
        client.instance.execute_via_ssh = False  # pyright: ignore
        assert wait_for_cloud_init(client, num_retries=60).ok
        if source.installs_new_version():
            client.install_new_cloud_init(
                source, take_snapshot=False, clean=False
            )
        logs = override_kernel_cmdline(ds_str, client)
        assert (
            "nocloud"
            == client.execute("cloud-init query platform").stdout.strip()
        )
        assert url_val in client.execute("cloud-init query subplatform").stdout
        assert (
            "Detected platform: DataSourceNoCloudNet [seed=None]"
            "[dsmode=net]. Checking for active instance data"
        ) in logs
