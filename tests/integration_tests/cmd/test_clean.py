# This file is part of cloud-init. See LICENSE file for license information.
import re

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.releases import IS_UBUNTU

USER_DATA = """\
#cloud-config
write_files:
- path: /etc/network/interfaces.d/50-cloud-init.cfg
  content: cloud-init test was here
  permissions: '0644'
  owner: root:root
- path: /etc/cloud/clean.d/runme.sh
  encoding: b64
  content: IyEvYmluL3NoCmVjaG8gIi9ldGMvY2xvdWQvY2xlYW4uZC9ydW5tZS5zaCBSQU4iCg==
  permissions: '0755'
  owner: root:root
- path: /etc/systemd/network/10-cloud-init-eth0.network
  content: cloud-init test was here
  permissions: '0644'
  owner: root:root
- path: /etc/cloud/clean.d/dontrunme.sh
  content: '#!/bin/sh\necho DID NOT RUN BECAUSE NO EXEC PERMS'
  permissions: '0644'
  owner: root:root
packages:
- logrotate
"""


@pytest.mark.user_data(USER_DATA)
class TestCleanCommand:
    @pytest.mark.skipif(
        not IS_UBUNTU, reason="Hasn't been tested on other distros"
    )
    def test_clean_rotated_logs(self, client: IntegrationInstance):
        """Clean with log params alters expected files without error"""
        assert client.execute("cloud-init status --wait --long").ok
        assert client.execute("logrotate /etc/logrotate.d/cloud-init").ok
        log_paths = (
            "/var/log/cloud-init.log",
            "/var/log/cloud-init.log.1.gz",
            "/var/log/cloud-init-output.log",
            "/var/log/cloud-init-output.log.1.gz",
        )

        assert client.execute("cloud-init clean --logs").ok
        for path in log_paths:
            assert client.execute(
                f"test -f {path}"
            ).failed, f"Unexpected file found {path}"

    def test_clean_by_param(self, client: IntegrationInstance):
        """Clean with various params alters expected files without error"""
        assert client.execute("cloud-init status --wait --long").ok
        result = client.execute("cloud-init clean")
        assert (
            result.ok
        ), "non-zero exit on cloud-init clean runparts of /etc/cloud/clean.d"
        # Log files are not removed without --logs
        log_paths = (
            "/var/log/cloud-init.log",
            "/var/log/cloud-init-output.log",
        )
        net_cfg_paths = (
            "/etc/network/interfaces.d/50-cloud-init.cfg",
            "/etc/netplan/50-cloud-init.yaml",
            "/etc/systemd/network/10-cloud-init-eth0.network",
        )
        for path in log_paths + net_cfg_paths:
            assert client.execute(
                f"test -f {path}"
            ).ok, f"Missing expected file {path}"
        # /etc/cloud/clean.d runparts scripts are run if executable
        assert result.stdout == "/etc/cloud/clean.d/runme.sh RAN"

        # Log files removed with --logs
        assert client.execute("cloud-init clean --logs").ok
        for path in log_paths:
            assert client.execute(
                f"test -f {path}"
            ).failed, f"Unexpected file found {path}"
        for path in net_cfg_paths:
            assert client.execute(
                f"test -f {path}"
            ).ok, f"Missing expected file {path}"

        prev_machine_id = client.read_from_file("/etc/machine-id")
        assert re.match(
            r"^[a-f0-9]{32}$", prev_machine_id
        ), f"Unexpected machine-id format {prev_machine_id}"

        # --machine-id sets /etc/machine-id
        assert client.execute("cloud-init clean --machine-id").ok
        machine_id = client.read_from_file("/etc/machine-id")
        assert machine_id != prev_machine_id
        assert "uninitialized" == machine_id

        # --configs remove network scope
        assert client.execute("cloud-init clean --configs network").ok

        for path in log_paths + net_cfg_paths:
            assert client.execute(
                f"test -f {path}"
            ).failed, f"Unexpected file found {path}"
