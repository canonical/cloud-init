"""NoCloud datasource integration tests."""

from textwrap import dedent

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from cloudinit.util import should_log_deprecation
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import (
    get_feature_flag_value,
    override_kernel_command_line,
    verify_clean_boot,
    verify_clean_log,
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
        version_boundary = get_feature_flag_value(
            client, "DEPRECATION_INFO_BOUNDARY"
        )
        # nocloud-net deprecated in version 24.1
        if should_log_deprecation("24.1", version_boundary):
            log_level = "DEPRECATED"
        else:
            log_level = "INFO"
        client.execute(
            rf"grep \"{log_level}]: The 'nocloud-net' datasource name is"
            ' deprecated" /var/log/cloud-init.log'
        ).ok


@pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Modifies grub config")
@pytest.mark.lxd_use_exec
class TestFTP:
    """Test nocloud's support for unencrypted FTP and FTP over TLS (ftps).

    These tests work by setting up a local ftp server on the test instance
    and then rebooting the instance clean (cloud-init clean --logs --reboot).

    Check for the existence (or non-existence) of specific log messages to
    verify functionality.
    """

    # should we really be surfacing this netplan stderr as a warning?
    # i.e. how does it affect the users?
    expected_warnings = [
        "Falling back to a hard restart of systemd-networkd.service"
    ]

    @staticmethod
    def _boot_with_cmdline(
        cmdline: str, client: IntegrationInstance, encrypted: bool = False
    ) -> None:
        """configure an ftp server to start prior to network timeframe
        optionally install certs and make the server support only FTP over TLS

        cmdline: a string containing the kernel command line set on reboot
        client: an instance to configure
        encrypted: a boolean which modifies the configured ftp server
        """

        # install the essential bits
        assert client.execute(
            "apt update && apt install -yq python3-pyftpdlib "
            "python3-openssl ca-certificates libnss3-tools"
        ).ok

        # How do you reliably run a ftp server for your instance to
        # read files from during early boot? In typical production
        # environments, the ftp server would be separate from the instance.
        #
        # For a reliable server that fits with the framework of running tests
        # on a single instance, it is easier to just install an ftp server
        # that runs on the second boot prior to the cloud-init unit which
        # reaches out to the ftp server. This achieves reaching out to an
        # ftp(s) server for testing - cloud-init just doesn't have to reach
        # very far to get what it needs.
        #
        # DO NOT use these concepts in a production.
        #
        # This configuration is neither secure nor production-grade - intended
        # only for testing purposes.
        client.write_to_file(
            "/server.py",
            dedent(
                """\
                #!/usr/bin/python3
                import logging

                from pyftpdlib.authorizers import DummyAuthorizer
                from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
                from pyftpdlib.servers import FTPServer
                from pyftpdlib.filesystems import UnixFilesystem

                encrypted = """
                + str(encrypted)
                + """

                logging.basicConfig(level=logging.DEBUG)

                # yeah, it's not secure but that's not the point
                authorizer = DummyAuthorizer()

                # Define a read-only anonymous user
                authorizer.add_anonymous("/home/anonymous")

                # Instantiate FTP handler class
                if not encrypted:
                    handler = FTPHandler
                    logging.info("Running unencrypted ftp server")
                else:
                    handler = TLS_FTPHandler
                    handler.certfile = "/cert.pem"
                    handler.keyfile = "/key.pem"
                    logging.info("Running encrypted ftp server")

                handler.authorizer = authorizer
                handler.abstracted_fs = UnixFilesystem
                server = FTPServer(("localhost", 2121), handler)

                # start the ftp server
                server.serve_forever()
                """
            ),
        )
        assert client.execute("chmod +x /server.py").ok

        if encrypted:
            if CURRENT_RELEASE > FOCAL:
                assert client.execute("apt install -yq mkcert").ok
            else:

                # install golang
                assert client.execute("apt install -yq golang").ok

                # build mkcert from source
                #
                # we could check out a tag, but the project hasn't
                # been updated in 2 years
                #
                # instructions from https://github.com/FiloSottile/mkcert
                assert client.execute(
                    "git clone https://github.com/FiloSottile/mkcert && "
                    "cd mkcert && "
                    "export latest_ver=$(git describe --tags --abbrev=0) && "
                    'wget "https://github.com/FiloSottile/mkcert/releases/'
                    "download/${latest_ver}/mkcert-"
                    '${latest_ver}-linux-amd64"'
                    " -O mkcert"
                ).ok

                # giddyup
                assert client.execute(
                    "ln -s $HOME/mkcert/mkcert /usr/local/bin/mkcert"
                ).ok

            # more palatable than openssl commands
            assert client.execute(
                "mkcert -install -cert-file /cert.pem -key-file /key.pem "
                "localhost 127.0.0.1 0.0.0.0 ::1"
            ).ok

        client.write_to_file(
            "/lib/systemd/system/local-ftp.service",
            dedent(
                """\
                [Unit]
                Description=TESTING USE ONLY ftp server
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
            ),
        )
        assert client.execute(
            "chmod 644 /lib/systemd/system/local-ftp.service"
        ).ok
        assert client.execute("systemctl enable local-ftp.service").ok
        assert client.execute("mkdir /home/anonymous").ok

        client.write_to_file(
            "/user-data",
            dedent(
                """\
                #cloud-config

                hostname: ftp-bootstrapper
                """
            ),
        )
        client.write_to_file(
            "/meta-data",
            dedent(
                """\
                instance-id: ftp-instance
                """
            ),
        )
        client.write_to_file("/vendor-data", "")

        # set the kernel command line, reboot with it
        override_kernel_command_line(cmdline, client)

    def test_nocloud_ftp_unencrypted_server_succeeds(
        self, client: IntegrationInstance
    ):
        """check that ftp:// succeeds to unencrypted ftp server

        this mode allows administrators to choose unencrypted ftp,
        at their own risk
        """
        cmdline = "ds=nocloud;seedfrom=ftp://0.0.0.0:2121"
        self._boot_with_cmdline(cmdline, client)
        verify_clean_boot(client, ignore_warnings=self.expected_warnings)
        assert "ftp-bootstrapper" == client.execute("hostname").rstrip()
        verify_clean_log(client.execute("cat /var/log/cloud-init.log").stdout)

    def test_nocloud_ftps_unencrypted_server_fails(
        self, client: IntegrationInstance
    ):
        """check that ftps:// fails to unencrypted ftp server

        this mode allows administrators to enforce TLS encryption
        """
        cmdline = "ds=nocloud;seedfrom=ftps://localhost:2121"
        self._boot_with_cmdline(cmdline, client)
        verify_clean_boot(
            client,
            ignore_warnings=self.expected_warnings,
            require_warnings=[
                "Getting data from <class 'cloudinit.sources.DataSourc"
                "eNoCloud.DataSourceNoCloudNet'> failed",
                "Used fallback datasource",
                "Attempted to connect to an insecure ftp server but used"
                " a scheme of ftps://, which is not allowed. Use ftp:// "
                "to allow connecting to insecure ftp servers.",
            ],
        )

    def test_nocloud_ftps_encrypted_server_succeeds(
        self, client: IntegrationInstance
    ):
        """check that ftps:// encrypted ftp server succeeds

        this mode allows administrators to enforce TLS encryption
        """
        cmdline = "ds=nocloud;seedfrom=ftps://localhost:2121"
        self._boot_with_cmdline(cmdline, client, encrypted=True)
        verify_clean_boot(client, ignore_warnings=self.expected_warnings)
        assert "ftp-bootstrapper" == client.execute("hostname").rstrip()
        verify_clean_log(client.execute("cat /var/log/cloud-init.log").stdout)

    def test_nocloud_ftp_encrypted_server_fails(
        self, client: IntegrationInstance
    ):
        """check that using ftp:// to encrypted ftp server fails"""
        cmdline = "ds=nocloud;seedfrom=ftp://0.0.0.0:2121"
        self._boot_with_cmdline(cmdline, client, encrypted=True)
        verify_clean_boot(client, ignore_warnings=self.expected_warnings)
