# See https://docs.pytest.org/en/stable/example
# /parametrize.html#parametrizing-conditional-raising
from contextlib import ExitStack as does_not_raise
from unittest import mock

import pytest

from cloudinit import net
from cloudinit.distros.networking import (
    BSDNetworking,
    LinuxNetworking,
    Networking,
)


@pytest.fixture
def generic_networking_cls():
    """Returns a direct Networking subclass which errors on /sys usage.

    This enables the direct testing of functionality only present on the
    ``Networking`` super-class, and provides a check on accidentally using /sys
    in that context.
    """

    class TestNetworking(Networking):
        def is_physical(self, *args, **kwargs):
            raise NotImplementedError

        def settle(self, *args, **kwargs):
            raise NotImplementedError

        def try_set_link_up(self, *args, **kwargs):
            raise NotImplementedError

    error = AssertionError("Unexpectedly used /sys in generic networking code")
    with mock.patch(
        "cloudinit.net.get_sys_class_path",
        side_effect=error,
    ):
        yield TestNetworking


@pytest.fixture
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


class TestBSDNetworkingTrySetLinkUp:
    def test_raises_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            BSDNetworking().try_set_link_up("eth0")


@mock.patch("cloudinit.net.is_up")
@mock.patch("cloudinit.distros.networking.subp.subp")
class TestLinuxNetworkingTrySetLinkUp:
    def test_calls_subp_return_true(self, m_subp, m_is_up):
        devname = "eth0"
        m_is_up.return_value = True
        is_success = LinuxNetworking().try_set_link_up(devname)

        assert (
            mock.call(["ip", "link", "set", devname, "up"])
            == m_subp.call_args_list[-1]
        )
        assert is_success

    def test_calls_subp_return_false(self, m_subp, m_is_up):
        devname = "eth0"
        m_is_up.return_value = False
        is_success = LinuxNetworking().try_set_link_up(devname)

        assert (
            mock.call(["ip", "link", "set", devname, "up"])
            == m_subp.call_args_list[-1]
        )
        assert not is_success


class TestBSDNetworkingSettle:
    def test_settle_doesnt_error(self):
        # This also implicitly tests that it doesn't use subp.subp
        BSDNetworking().settle()


@pytest.mark.usefixtures("sys_class_net")
@mock.patch("cloudinit.distros.networking.util.udevadm_settle", autospec=True)
class TestLinuxNetworkingSettle:
    def test_no_arguments(self, m_udevadm_settle):
        LinuxNetworking().settle()

        assert [mock.call(exists=None)] == m_udevadm_settle.call_args_list

    def test_exists_argument(self, m_udevadm_settle):
        LinuxNetworking().settle(exists="ens3")

        expected_path = net.sys_dev_path("ens3")
        assert [
            mock.call(exists=expected_path)
        ] == m_udevadm_settle.call_args_list


class TestNetworkingWaitForPhysDevs:
    @pytest.fixture
    def wait_for_physdevs_netcfg(self):
        """This config is shared across all the tests in this class."""

        def ethernet(mac, name, driver=None, device_id=None):
            v2_cfg = {"set-name": name, "match": {"macaddress": mac}}
            if driver:
                v2_cfg["match"].update({"driver": driver})
            if device_id:
                v2_cfg["match"].update({"device_id": device_id})

            return v2_cfg

        physdevs = [
            ["aa:bb:cc:dd:ee:ff", "eth0", "virtio", "0x1000"],
            ["00:11:22:33:44:55", "ens3", "e1000", "0x1643"],
        ]
        netcfg = {
            "version": 2,
            "ethernets": {args[1]: ethernet(*args) for args in physdevs},
        }
        return netcfg

    def test_skips_settle_if_all_present(
        self,
        generic_networking_cls,
        wait_for_physdevs_netcfg,
    ):
        networking = generic_networking_cls()
        with mock.patch.object(
            networking, "get_interfaces_by_mac"
        ) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.side_effect = iter(
                [{"aa:bb:cc:dd:ee:ff": "eth0", "00:11:22:33:44:55": "ens3"}]
            )
            with mock.patch.object(
                networking, "settle", autospec=True
            ) as m_settle:
                networking.wait_for_physdevs(wait_for_physdevs_netcfg)
            assert 0 == m_settle.call_count

    def test_calls_udev_settle_on_missing(
        self,
        generic_networking_cls,
        wait_for_physdevs_netcfg,
    ):
        networking = generic_networking_cls()
        with mock.patch.object(
            networking, "get_interfaces_by_mac"
        ) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.side_effect = iter(
                [
                    {
                        "aa:bb:cc:dd:ee:ff": "eth0"
                    },  # first call ens3 is missing
                    {
                        "aa:bb:cc:dd:ee:ff": "eth0",
                        "00:11:22:33:44:55": "ens3",
                    },  # second call has both
                ]
            )
            with mock.patch.object(
                networking, "settle", autospec=True
            ) as m_settle:
                networking.wait_for_physdevs(wait_for_physdevs_netcfg)
            m_settle.assert_called_with(exists="ens3")

    @pytest.mark.parametrize(
        "strict,expectation",
        [(True, pytest.raises(RuntimeError)), (False, does_not_raise())],
    )
    def test_retrying_and_strict_behaviour(
        self,
        strict,
        expectation,
        generic_networking_cls,
        wait_for_physdevs_netcfg,
    ):
        networking = generic_networking_cls()
        with mock.patch.object(
            networking, "get_interfaces_by_mac"
        ) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.return_value = {}

            with mock.patch.object(
                networking, "settle", autospec=True
            ) as m_settle:
                with expectation:
                    networking.wait_for_physdevs(
                        wait_for_physdevs_netcfg, strict=strict
                    )

        assert (
            5 * len(wait_for_physdevs_netcfg["ethernets"])
            == m_settle.call_count
        )
