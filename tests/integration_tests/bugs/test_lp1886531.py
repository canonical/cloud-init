"""Integration test for LP: #1886531

This test replicates the failure condition (absent /etc/fstab) on all releases
by removing it in a bootcmd; this runs well before the part of cloud-init which
causes the failure.

The only required assertion is that cloud-init does not emit a WARNING to the
log: this indicates that the fstab parsing code has not failed.

https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/1886531
"""
import pytest

from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
bootcmd:
- rm -f /etc/fstab
"""


class TestLp1886531:
    @pytest.mark.user_data(USER_DATA)
    def test_lp1886531(self, client):
        log_content = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log_content)
