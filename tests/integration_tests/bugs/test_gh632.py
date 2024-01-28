"""Integration test for gh-632.

Verify that if cloud-init is using DataSourceRbxCloud, there is
no traceback if the metadata disk cannot be found.
"""
import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_log


# With some datasource hacking, we can run this on a NoCloud instance
@pytest.mark.skipif(
    PLATFORM not in ["lxd_container", "lxd_vm"],
    reason="Tested behavior is emulated using NoCloud",
)
def test_datasource_rbx_no_stacktrace(client: IntegrationInstance):
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/90_dpkg.cfg",
        "datasource_list: [ RbxCloud, NoCloud, LXD ]\n",
    )
    client.write_to_file(
        "/etc/cloud/ds-identify.cfg",
        "policy: enabled\n",
    )
    client.execute("cloud-init clean --logs")
    client.restart()

    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert "Failed to load metadata and userdata" not in log
    assert (
        "Getting data from <class 'cloudinit.sources.DataSourceRbxCloud."
        "DataSourceRbxCloud'> failed" not in log
    )
