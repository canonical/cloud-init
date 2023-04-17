import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM


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
            "ds=nocloud;s=http://my-url/",
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


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
@pytest.mark.parametrize("ds_str", ("ci.ds=nocloud-net",))
def test_lxd_datasource_kernel_override_nocloud_net(
    ds_str, client: IntegrationInstance
):
    """NoCloud requirements vary slightly from other datasources with parsing
    nocloud-net due to historical reasons. Do to this variation, this is
    implemented in NoCloud's ds_detect and therefore has a different log
    message.
    """

    assert (
        "Machine is running on DataSourceNoCloud [seed=None][dsmode=net]."
    ) in override_kernel_cmdline(ds_str, client)
