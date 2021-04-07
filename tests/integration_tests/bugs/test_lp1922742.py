"""Integration test for LP: #1922742

cloud-init fails to resize and fails on any non-LVM root partitions in KVM.

This test checks that cloud-init doesn't fail to resize partitions on KVM for
non-LVM root partitions.
TODO: It should also setup an lvm partition and verify that lvm resizing works.
"""
import pytest


@pytest.mark.lxd_vm
@pytest.mark.lxd_use_exec
@pytest.mark.ubuntu
class TestLVMResize:
    def test_sucess_resize2fs_and_no_errors_from_growpart_on_non_lvm(
        self, client
    ):
        assert client.execute('cloud-init status --wait --long').ok is True
        log = client.read_from_file('/var/log/cloud-init.log')
        assert "SUCCESS: config-growpart ran successfully" in log
        assert "Running command ('resize2fs', '/dev/sda1')" in log
        assert "'/' resized" in log
