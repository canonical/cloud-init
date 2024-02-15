"""NoCloud datasource integration tests."""
import os
from textwrap import dedent

import pytest

from cloudinit.subp import subp
from pycloudlib.lxd.instance import LXDInstance
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.test_kernel_commandline_match import (
    override_kernel_cmdline,
)

VENDOR_DATA = """\
#cloud-config
runcmd:
  - touch /var/tmp/seeded_vendordata_test_file
"""


LXD_METADATA_NOCLOUD_SEED = """\
  /var/lib/cloud/seed/nocloud-net/meta-data:
    when:
    - create
    - copy
    create_only: false
    template: emptycfg.tpl
    properties:
      default: |
        #cloud-config
        {}
  /var/lib/cloud/seed/nocloud-net/user-data:
    when:
    - create
    - copy
    create_only: false
    template: emptycfg.tpl
    properties:
      default: |
        #cloud-config
        {}
"""


def setup_nocloud(instance: LXDInstance):
    # On Jammy and above, LXD no longer uses NoCloud, so we need to set
    # it up manually
    lxd_image_metadata = subp(
        ["lxc", "config", "metadata", "show", instance.name]
    )
    if "/var/lib/cloud/seed/nocloud-net" in lxd_image_metadata.stdout:
        return
    subp(
        ["lxc", "config", "template", "create", instance.name, "emptycfg.tpl"],
    )
    subp(
        ["lxc", "config", "template", "edit", instance.name, "emptycfg.tpl"],
        data="#cloud-config\n{}\n",
    )
    subp(
        ["lxc", "config", "metadata", "edit", instance.name],
        data=f"{lxd_image_metadata.stdout}{LXD_METADATA_NOCLOUD_SEED}",
    )


@pytest.mark.lxd_setup.with_args(setup_nocloud)
@pytest.mark.lxd_use_exec
@pytest.mark.skipif(
    PLATFORM != "lxd_container",
    reason="Requires NoCloud with custom setup",
)
def test_nocloud_seedfrom_vendordata(client: IntegrationInstance):
    """Integration test for #570.

    Test that we can add optional vendor-data to the seedfrom file in a
    NoCloud environment
    """
    seed_dir = "/var/tmp/test_seed_dir"
    result = client.execute(
        "mkdir {seed_dir} && "
        "touch {seed_dir}/user-data && "
        "touch {seed_dir}/meta-data && "
        "echo 'seedfrom: {seed_dir}/' > "
        "/var/lib/cloud/seed/nocloud-net/meta-data".format(seed_dir=seed_dir)
    )
    assert result.return_code == 0

    client.write_to_file(
        "{}/vendor-data".format(seed_dir),
        VENDOR_DATA,
    )
    client.execute("cloud-init clean --logs")
    client.restart()
    assert client.execute("cloud-init status").ok
    assert "seeded_vendordata_test_file" in client.execute("ls /var/tmp")


SMBIOS_USERDATA = """\
#cloud-config
runcmd:
  - touch /var/tmp/smbios_test_file
"""
SMBIOS_SEED_DIR = "/smbios_seed"


def setup_nocloud_local_serial(instance: LXDInstance):
    subp(
        [
            "lxc",
            "config",
            "set",
            instance.name,
            "raw.qemu=-smbios "
            f"type=1,serial=ds=nocloud;s=file://{SMBIOS_SEED_DIR};h=myhost",
        ]
    )


def setup_nocloud_network_serial(instance: LXDInstance):
    subp(
        [
            "lxc",
            "config",
            "set",
            instance.name,
            "raw.qemu=-smbios "
            "type=1,serial=ds=nocloud-net;s=http://0.0.0.0/;h=myhost",
        ]
    )


@pytest.mark.lxd_use_exec
@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Requires NoCloud with raw QEMU serial setup",
)
class TestSmbios:
    @pytest.mark.lxd_setup.with_args(setup_nocloud_local_serial)
    def test_smbios_seed_local(self, client: IntegrationInstance):
        """Check that smbios seeds that use local disk work"""
        assert client.execute(f"mkdir -p {SMBIOS_SEED_DIR}").ok
        client.write_to_file(f"{SMBIOS_SEED_DIR}/user-data", SMBIOS_USERDATA)
        client.write_to_file(f"{SMBIOS_SEED_DIR}/meta-data", "")
        client.write_to_file(f"{SMBIOS_SEED_DIR}/vendor-data", "")
        assert client.execute("cloud-init clean --logs").ok
        client.restart()
        assert client.execute("test -f /var/tmp/smbios_test_file").ok

    @pytest.mark.lxd_setup.with_args(setup_nocloud_network_serial)
    def test_smbios_seed_network(self, client: IntegrationInstance):
        """Check that smbios seeds that use network (http/https) work"""
        service_file = "/lib/systemd/system/local-server.service"
        client.write_to_file(
            service_file,
            dedent(
                """\
                [Unit]
                Description=Serve a local webserver
                Before=cloud-init.service
                Wants=cloud-init-local.service
                DefaultDependencies=no
                After=systemd-networkd-wait-online.service
                After=networking.service


                [Install]
                WantedBy=cloud-init.target

                [Service]
                """
                f"WorkingDirectory={SMBIOS_SEED_DIR}"
                """
                ExecStart=/usr/bin/env python3 -m http.server --bind 0.0.0.0 80
                """
            ),
        )
        assert client.execute(
            "chmod 644 /lib/systemd/system/local-server.service"
        ).ok
        assert client.execute("systemctl enable local-server.service").ok
        client.write_to_file(
            "/etc/cloud/cloud.cfg.d/91_do_not_use_lxd.cfg",
            "datasource_list: [ NoCloud, None ]\n",
        )
        assert client.execute(f"mkdir -p {SMBIOS_SEED_DIR}").ok
        client.write_to_file(f"{SMBIOS_SEED_DIR}/user-data", SMBIOS_USERDATA)
        client.write_to_file(f"{SMBIOS_SEED_DIR}/meta-data", "")
        client.write_to_file(f"{SMBIOS_SEED_DIR}/vendor-data", "")
        assert client.execute("cloud-init clean --logs").ok
        client.restart()
        assert client.execute("test -f /var/tmp/smbios_test_file").ok
        assert "'nocloud-net' datasource name is deprecated" in client.execute(
            "cloud-init status --format json"
        )

@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
def test_nocloud_ftp(client: IntegrationInstance):
    # creating an ftp service to run prior
    # to cloud-config is bonkers, lets
    # hope that users don't see this kind of
    # test code as an example to follow

    client.execute("apt update && apt install -yq python3-pyftpdlib")

    client.write_to_file(
        "/server.py",
        dedent(
            """\
            #!/usr/bin/python3
            from pyftpdlib.authorizers import DummyAuthorizer
            from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
            from pyftpdlib.servers import FTPServer
            from pyftpdlib.filesystems import UnixFilesystem

            # yeah, it's not secure but that's not the point
            authorizer = DummyAuthorizer()

            # Define a read-only anonymous user
            authorizer.add_anonymous("/home/anonymous")

            # Instantiate FTP handler class
            handler = FTPHandler
            handler.authorizer = authorizer
            handler.abstracted_fs = UnixFilesystem
            server = FTPServer(("localhost", 2121), handler)

            # start the ftp server
            server.serve_forever()
            """
        ),
    )
    client.execute("chmod +x /server.py")
    client.write_to_file(
        "/lib/systemd/system/local-ftp.service",
        dedent(
            """\
            [Unit]
            Description=run a local ftp server against
            Wants=cloud-init-local.service
            DefaultDependencies=no

            # we want the network up for network operations
            # and NoCloud operates in network timeframe
            After=systemd-networkd-wait-online.service
            After=networking.service
            Before=cloud-init.service

            [Service]
            Type=exec
            ExecStart=/server.py

            [Install]
            WantedBy=cloud-init.target
            """
        )
    )
    client.execute("chmod 644 /lib/systemd/system/local-ftp.service")
    client.execute("systemctl enable local-ftp.service")

    client.execute("mkdir /home/anonymous/")
    client.write_to_file(
        "/home/anonymous/user-data",
        dedent(
            """
            #cloud-config

            hostname: ftp-bootstrapper
            """
        )
    )
    client.write_to_file(
        "/home/anonymous/meta-data",
        dedent(
            """
            instance-id: ftp-instance
            """
        )
    )
    client.write_to_file("/home/anonymous/vendor-data", "")

    # set the kernel commandline, reboot with it
    override_kernel_cmdline(
        "ds=nocloud;seedfrom=ftp://0.0.0.0:2121", client
    )
