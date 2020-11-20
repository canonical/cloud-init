""" Integration test for LP #187099

Ensure that if fallocate fails during mkswap that we fall back to using dd

https://bugs.launchpad.net/cloud-init/+bug/1897099
"""

import pytest


USER_DATA = """\
#cloud-config
swap:
  filename: /swap.img
  size: 10000000
  maxsize: 10000000
"""


@pytest.mark.user_data(USER_DATA)
@pytest.mark.lxd_vm
def test_fallocate_fallback(client):
    # Setup instance
    client.execute('swapoff -a')
    client.execute('rm -r /swap.img')
    client.execute("echo 'whoops' > /usr/bin/fallocate")

    # Reset instance state
    client.execute('cloud-init clean --logs && sync')
    client.instance.restart()
    client.instance.wait(raise_on_cloudinit_failure=False)

    # Verify
    log = client.read_from_file('/var/log/cloud-init.log')
    assert '/swap.img' in client.execute('cat /proc/swaps')
    assert '/swap.img' in client.execute('cat /etc/fstab')
    assert 'fallocate swap creation failed, will attempt with dd' in log
    assert "Running command ['dd', 'if=/dev/zero', 'of=/swap.img'" in log
    assert 'SUCCESS: config-mounts ran successfully' in log
