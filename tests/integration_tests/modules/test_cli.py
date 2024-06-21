"""Integration tests for CLI functionality

These would be for behavior manually invoked by user from the command line
"""

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE

VALID_USER_DATA = """\
#cloud-config
runcmd:
  - echo 'hi' > /var/tmp/test
"""

INVALID_USER_DATA_HEADER = """\
runcmd:
  - echo 'hi' > /var/tmp/test
"""

FAILING_USER_DATA = """\
#cloud-config
bootcmd:
  - exit 1
runcmd:
  - exit 1
"""

# The '-' in 'hashed-password' fails schema validation
INVALID_USER_DATA_SCHEMA = """\
#cloud-config
users:
  - default
  - name: newsuper
    gecos: Big Stuff
    groups: users, admin
    sudo: ALL=(ALL) NOPASSWD:ALL
    hashed-password: asdfasdf
    shell: /bin/bash
    lock_passwd: true
"""


@pytest.mark.user_data(VALID_USER_DATA)
class TestValidUserData:
    def test_schema_status(self, class_client: IntegrationInstance):
        """Test `cloud-init schema` with valid userdata.

        PR #575
        """
        result = class_client.execute("cloud-init schema --system")
        assert result.ok
        assert "Valid schema user-data" in result.stdout.strip()
        result = class_client.execute("cloud-init status --long")
        assert 0 == result.return_code, (
            f"Unexpected exit {result.return_code} from cloud-init status:"
            f" {result}"
        )

    def test_modules_init(self, class_client: IntegrationInstance):
        for mode in ("init", "config", "final"):
            result = class_client.execute(f"cloud-init modules --mode {mode}")
            assert result.ok
            assert f"'modules:{mode}'" in result.stdout.strip()


@pytest.mark.skipif(
    PLATFORM == "qemu", reason="QEMU only supports #cloud-config userdata"
)
@pytest.mark.user_data(INVALID_USER_DATA_HEADER)
def test_invalid_userdata(client: IntegrationInstance):
    """Test `cloud-init schema` with invalid userdata.

    PR #575
    """
    result = client.execute("cloud-init schema --system")
    assert not result.ok
    assert "Cloud config schema errors" in result.stderr
    assert (
        "Expected first line to be one of: #!, ## template: jinja,"
        " #cloud-boothook, #cloud-config" in result.stderr
    )
    result = client.execute("cloud-init status --long")
    if CURRENT_RELEASE.series in ("focal", "jammy", "lunar", "mantic"):
        return_code = 0  # Stable releases don't change exit code behavior
    else:
        return_code = 2  # 23.4 and later will exit 2 on warnings
    assert (
        return_code == result.return_code
    ), f"Unexpected exit code {result.return_code}"


@pytest.mark.user_data(INVALID_USER_DATA_SCHEMA)
def test_invalid_userdata_schema(client: IntegrationInstance):
    """Test invalid schema represented as Warnings, not fatal

    PR #1175
    """
    result = client.execute("cloud-init status --long")
    if CURRENT_RELEASE.series in ("focal", "jammy", "lunar", "mantic"):
        return_code = 0  # Stable releases don't change exit code behavior
    else:
        return_code = 2  # 23.4 and later will exit 2 on warnings
    assert (
        return_code == result.return_code
    ), f"Unexpected exit code {result.return_code}"
    log = client.read_from_file("/var/log/cloud-init.log")
    warning = (
        "[WARNING]: cloud-config failed schema validation! "
        "You may run 'sudo cloud-init schema --system' to check the details."
    )
    assert warning in log
    assert "asdfasdf" not in log


@pytest.mark.user_data(FAILING_USER_DATA)
def test_failing_userdata_modules_exit_codes(client: IntegrationInstance):
    """Test failing in modules representd in exit status.

    To ensure we don't miss any errors or warnings if a service happens
    to be restarted, any further module invocations will exit with error
    on the same boot if a previous invocation exited with error.

    In this test, both bootcmd and runcmd will exit with error the first time.
    The second time, runcmd will run cleanly, but still exit with error.
    Since bootcmd runs in init timeframe, and runcmd runs in final timeframe,
    expect error from those two modes.
    """
    for mode in ("init", "config", "final"):
        result = client.execute(f"cloud-init modules --mode {mode}")
        assert result.ok if mode == "config" else result.failed
        assert f"'modules:{mode}'" in result.stdout.strip()
