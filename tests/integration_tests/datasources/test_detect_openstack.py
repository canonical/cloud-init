import pytest

from tests.integration_tests.instances import IntegrationInstance


@pytest.mark.lxd_vm
@pytest.mark.lxd_container
@pytest.mark.lxd_use_exec
def test_lxd_datasource_kernel_override(client: IntegrationInstance):
    """This test is twofold: it tests kernel commandline override, which also
    validates OpenStack Ironic requirements. OpenStack Ironic does not
    advertise itself to cloud-init via any of the conventional methods: DMI,
    etc.

    On systemd, ds-identify is able to grok kernel commandline, however to
    support cloud-init kernel command line parsing on non-systemd, parsing
    kernel commandline in Python code is required.

    This test runs on LXD, but forces cloud-init to attempt to run OpenStack.
    This will inevitably fail on LXD, but we only care that it tried - on
    Ironic it will succeed.

    Configure grub's kernel command line to tell cloud-init to use OpenStack
    - even though LXD should naturally be detected.
    """
    client.execute(
        "sed --in-place "
        '\'s/^.*GRUB_CMDLINE_LINUX=.*$/GRUB_CMDLINE_LINUX="ci.ds=OpenStack"/g'
        "' /etc/default/grub"
    )

    # We should probably include non-systemd distros at some point. This should
    # most likely be as simple as updating the output path for grub-mkconfig
    client.execute("grub-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg")
    client.execute("cloud-init clean --logs")
    client.instance.shutdown()
    client.instance.execute_via_ssh = False
    client.instance.start()
    client.execute("cloud-init status --wait")
    log = client.execute("cat /var/log/cloud-init.log")
    assert (
        "Machine is configured by the kernel commandline to run on single "
        "datasource DataSourceOpenStackLocal"
    ) in log
