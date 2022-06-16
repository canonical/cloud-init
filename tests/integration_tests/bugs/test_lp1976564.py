"""Integration test for LP: #1976564

cloud-init must honor the cloud-dir configured in /etc/cloud/cloud.cfg.d
"""
import re
from typing import Iterator

import pytest

from tests.integration_tests.instances import IntegrationInstance
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
    cfg = tmpdir.join(CUSTOM_CLOUD_DIR_FN)
    with open(cfg, "w") as f:
        f.write(CUSTOM_CLOUD_DIR)
    client.push_file(cfg, f"/etc/cloud/cloud.cfg.d/{CUSTOM_CLOUD_DIR_FN}")
    client.execute(f"rm -rf {DEFAULT_CLOUD_DIR}")  # Remove previous cloud_dir
    client.execute("cloud-init clean --logs")
    client.restart()
    yield client


@pytest.mark.lxd_container
@pytest.mark.lxd_vm
class TestLp1976564:
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
        collect_logs_result = custom_client.execute(
            "cloud-init collect-logs --include-userdata"
        )
        assert (
            collect_logs_result.ok
        ), f"collect-logs error: {collect_logs_result.stderr}"

    def test_lp1976564(self, custom_client: IntegrationInstance):
        self.verify_log_and_files(custom_client)
        self.collect_logs(custom_client)
