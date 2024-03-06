import os
import re
from datetime import datetime
from typing import Iterator

import pytest

from cloudinit.cmd.devel.logs import (
    INSTALLER_APPORT_FILES,
    INSTALLER_APPORT_SENSITIVE_FILES,
)
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import verify_clean_log

DEFAULT_CLOUD_DIR = "/var/lib/cloud"
NEW_CLOUD_DIR = "/new-cloud-dir"
CUSTOM_CLOUD_DIR = f"""\
system_info:
  paths:
    cloud_dir: {NEW_CLOUD_DIR}
"""
CUSTOM_CLOUD_DIR_FN = "95-custom-cloud-dir.cfg"


@pytest.fixture
def custom_client(
    client: IntegrationInstance, tmpdir
) -> Iterator[IntegrationInstance]:
    client.write_to_file(
        f"/etc/cloud/cloud.cfg.d/{CUSTOM_CLOUD_DIR_FN}", CUSTOM_CLOUD_DIR
    )
    client.execute(f"rm -rf {DEFAULT_CLOUD_DIR}")  # Remove previous cloud_dir
    client.execute("cloud-init clean --logs")
    client.restart()
    yield client


class TestHonorCloudDir:
    def verify_log_and_files(self, custom_client):
        log_content = custom_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)
        assert NEW_CLOUD_DIR in log_content
        assert DEFAULT_CLOUD_DIR not in log_content
        assert custom_client.execute(f"test ! -d {DEFAULT_CLOUD_DIR}").ok

    def collect_logs(self, custom_client: IntegrationInstance):
        help_result = custom_client.execute("cloud-init collect-logs -h")
        assert help_result.ok, help_result.stderr
        assert f"{NEW_CLOUD_DIR}/instance/user-data.txt" in re.sub(
            r"\s+", "", help_result.stdout
        ), "user-data file not correctly render in collect-logs -h"

        # Touch a couple of subiquity files to assert collected
        installer_files = (
            INSTALLER_APPORT_FILES[-1],
            INSTALLER_APPORT_SENSITIVE_FILES[-1],
        )

        for apport_file in installer_files:
            custom_client.execute(
                f"mkdir -p {os.path.dirname(apport_file.path)}"
            )
            custom_client.execute(f"touch {apport_file.path}")

        collect_logs_result = custom_client.execute(
            "cloud-init collect-logs --include-userdata"
        )
        assert (
            collect_logs_result.ok
        ), f"collect-logs error: {collect_logs_result.stderr}"
        found_logs = custom_client.execute(
            "tar -tf cloud-init.tar.gz"
        ).stdout.splitlines()
        dirname = datetime.utcnow().date().strftime("cloud-init-logs-%Y-%m-%d")
        expected_logs = [
            f"{dirname}/",
            f"{dirname}/cloud-init.log",
            f"{dirname}/cloud-init-output.log",
            f"{dirname}/dmesg.txt",
            f"{dirname}/user-data.txt",
            f"{dirname}/version",
            f"{dirname}/dpkg-version",
            f"{dirname}/journal.txt",
            f"{dirname}/run/",
            f"{dirname}/run/cloud-init/",
            f"{dirname}/run/cloud-init/result.json",
            f"{dirname}/run/cloud-init/.instance-id",
            f"{dirname}/run/cloud-init/cloud-init-generator.log",
            f"{dirname}/run/cloud-init/enabled",
            f"{dirname}/run/cloud-init/cloud-id",
            f"{dirname}/run/cloud-init/instance-data.json",
            f"{dirname}/run/cloud-init/instance-data-sensitive.json",
            f"{dirname}{installer_files[0].path}",
            f"{dirname}{installer_files[1].path}",
        ]
        for log in expected_logs:
            assert log in found_logs
        # Assert disabled cloud-init collect-logs grabs /var/lib/cloud/data
        custom_client.execute("touch /run/cloud-init/disabled")
        assert custom_client.execute(
            "cloud-init collect-logs --include-userdata"
        ).ok
        found_logs = custom_client.execute(
            "tar -tf cloud-init.tar.gz"
        ).stdout.splitlines()
        dirname = datetime.utcnow().date().strftime("cloud-init-logs-%Y-%m-%d")
        assert f"{dirname}/new-cloud-dir/data/result.json" in found_logs

    # LXD inserts some agent setup code into VMs on Bionic under
    # /var/lib/cloud. The inserted script will cause this test to fail
    # because the test ensures nothing is running under /var/lib/cloud.
    # Since LXD is doing this and not cloud-init, we should just not run
    # on Bionic to avoid it.
    @pytest.mark.skipif(
        CURRENT_RELEASE < FOCAL,
        reason="LXD inserts conflicting setup on releases prior to focal",
    )
    def test_honor_cloud_dir(self, custom_client: IntegrationInstance):
        """Integration test for LP: #1976564

        cloud-init must honor the cloud-dir configured in
        /etc/cloud/cloud.cfg.d
        """
        self.verify_log_and_files(custom_client)
        self.collect_logs(custom_client)
