# This file is part of cloud-init. See LICENSE file for license information.
import os

import pytest

from cloudinit import platform, util


@pytest.mark.usefixtures("fake_filesystem")
class TestPlatformDetection:
    def test_secureboot_detection_present(self):
        util.ensure_dir(os.path.join("sys", "firmware", "efi", "efivars"))
        util.write_file("/sys/firmware/efi/efivars/SecureBoot-1234", b"x")
        assert (
            platform.sub_platform_vars("a/__platform.secureboot__/b")
            == "a/true/b"
        )

    def test_secureboot_detection_absent(self):
        assert (
            platform.sub_platform_vars("a/__platform.secureboot__/b") == "a//b"
        )

    def test_tpm2_detection_present(self):
        util.ensure_dir("dev")
        util.write_file("/dev/tpm0", b"")
        assert platform.sub_platform_vars("__platform.tpm2__") == "true"

    def test_tpm2_detection_absent(self):
        assert platform.sub_platform_vars("__platform.tpm2__") == ""

    def test_virtualized_fallback_cpuinfo(self, mocker):
        # detect virtualization via /proc/cpuinfo 'hypervisor' flag
        mocker.patch("cloudinit.platform.is_container", return_value=False)
        util.write_file("/proc/cpuinfo", b"flags : fpu vme hypervisor abc")
        assert (
            platform.sub_platform_vars("__platform.virtualized__")
            == "hypervisor"
        )

    def test_invalid_key_warns(self, caplog):
        platform.sub_platform_vars("__platform.notakey__")
        assert "Ignoring invalid __platform.notakey__" in caplog.text
