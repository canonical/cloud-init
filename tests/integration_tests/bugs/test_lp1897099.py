"""Integration test for LP #187099

Ensure that if fallocate fails during mkswap that we fall back to using dd

https://bugs.launchpad.net/cloud-init/+bug/1897099
"""

import pytest

from tests.integration_tests.integration_settings import PLATFORM

USER_DATA = """\
#cloud-config
bootcmd:
  - echo 'whoops' > /usr/bin/fallocate
swap:
  filename: /swap.img
  size: 10000000
  maxsize: 10000000
"""


@pytest.mark.user_data(USER_DATA)
@pytest.mark.skipif(
    PLATFORM == "lxd_container", reason="Containers cannot configure swap"
)
def test_fallocate_fallback(client):
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "/swap.img" in client.execute("cat /proc/swaps")
    assert "/swap.img" in client.execute("cat /etc/fstab")
    assert "fallocate swap creation failed, will attempt with dd" in log
    assert "Running command ['dd', 'if=/dev/zero', 'of=/swap.img'" in log
    assert "SUCCESS: config-mounts ran successfully" in log
