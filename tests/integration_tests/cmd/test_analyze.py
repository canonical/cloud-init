# This file is part of cloud-init. See LICENSE file for license information.
"""Tests for `cloud-init analyze`"""
import pytest

from cloudinit.distros import uses_systemd
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import get_datetime_from_string


class TestAnalyzeCommand:
    @pytest.mark.skipif(not uses_systemd(), reason="Relies on systemd output")
    @pytest.mark.skipif(
        PLATFORM != "lxd_container",
        reason="Testing lxdcontainer-specific behavior",
    )
    def test_analyze_boot_ordered_timestamps(self, module_client):
        """
        Confirm that analyze boot is working correctly in lxd containers
        and that the correct zero-point is used for the monotonic clock used
        to determine when cloud-init was activated by systemd
        """
        assert module_client.execute("cloud-init status --wait --long").ok
        result = module_client.execute("cloud-init analyze boot")
        assert result.stderr == "container"

        container_start_time = get_datetime_from_string(
            result.stdout, "^\\s*Container started at: (.+?)$"
        )
        cloudinit_activation_time = get_datetime_from_string(
            result.stdout, "^\\s*Cloud-init activated by systemd at: (.+?)$"
        )
        cloudinit_start_time = get_datetime_from_string(
            result.stdout, "^\\s*Cloud-init start: (.+?)$"
        )
        assert container_start_time < cloudinit_activation_time
        assert cloudinit_activation_time < cloudinit_start_time
