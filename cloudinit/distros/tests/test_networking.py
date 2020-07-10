from unittest import mock

import pytest

from cloudinit.distros.networking import BSDNetworking, LinuxNetworking


@pytest.yield_fixture
def sys_class_net(tmpdir):
    sys_class_net_path = tmpdir.join("sys/class/net")
    sys_class_net_path.ensure_dir()
    with mock.patch(
        "cloudinit.net.get_sys_class_path",
        return_value=sys_class_net_path.strpath + "/",
    ):
        yield sys_class_net_path


class TestBSDNetworkingIsPhysical:
    def test_raises_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            BSDNetworking().is_physical("eth0")


class TestLinuxNetworkingIsPhysical:
    def test_returns_false_by_default(self, sys_class_net):
        assert not LinuxNetworking().is_physical("eth0")

    def test_returns_false_if_devname_exists_but_not_physical(
        self, sys_class_net
    ):
        devname = "eth0"
        sys_class_net.join(devname).mkdir()
        assert not LinuxNetworking().is_physical(devname)

    def test_returns_true_if_device_is_physical(self, sys_class_net):
        devname = "eth0"
        device_dir = sys_class_net.join(devname)
        device_dir.mkdir()
        device_dir.join("device").write("")

        assert LinuxNetworking().is_physical(devname)
