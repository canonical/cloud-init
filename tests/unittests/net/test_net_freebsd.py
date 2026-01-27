# tests/unittests/net/test_net_freebsd.py
#
# FreeBSD-specific networking tests
#
# These tests validate Azure + FreeBSD edge cases involving
# duplicate MAC addresses, Hyper-V synthetic NICs (hn*),
# accelerated VFs (mce*), and deterministic primary NIC selection.

import logging
from unittest import mock

from cloudinit import net

LOG = logging.getLogger(__name__)


@mock.patch("cloudinit.net.util.is_FreeBSD", return_value=True)
@mock.patch("cloudinit.net.subp.subp")
def test_freebsd_duplicate_mac_preserves_first_interface(
    m_subp, _is_freebsd, caplog
):
    """Duplicate MACs on FreeBSD must not drop the synthetic hn* NIC.

    Azure exposes hn* (synthetic) and mce* (accelerated VF) interfaces
    with the same MAC address. The first-discovered interface must be
    preserved and the duplicate logged.
    """
    caplog.set_level(logging.DEBUG)

    def subp_side_effect(cmd, *args, **kwargs):
        if cmd == ["ifconfig", "-a", "ether"]:
            return (
                "\n\n".join(
                    [
                        "\n".join(
                            [
                                "hn0: flags=8843"
                                "<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST>",
                                "\tether aa:bb:cc:dd:ee:ff",
                            ]
                        ),
                        "\n".join(
                            [
                                "mce0: flags=8843"
                                "<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST>",
                                "\tether aa:bb:cc:dd:ee:ff",
                            ]
                        ),
                    ]
                ),
                "",
            )
        raise AssertionError(f"Unexpected subp call: {cmd}")

    m_subp.side_effect = subp_side_effect

    interfaces = net.get_interfaces_by_mac_on_freebsd()

    assert "hn0" in interfaces.values()
    assert "Duplicate MAC" in caplog.text


@mock.patch("cloudinit.net.util.is_FreeBSD", return_value=True)
@mock.patch("cloudinit.net.subp.subp")
def test_freebsd_get_devicelist_returns_all_interfaces(m_subp, _is_freebsd):
    """FreeBSD device discovery must not drop interfaces due to MAC collisions.

    get_devicelist() should enumerate all interfaces directly rather than
    relying on MAC-keyed maps.
    """
    m_subp.return_value = ("hn0 mce0 lo0", "")

    devices = net.get_devicelist()

    assert "hn0" in devices
    assert "mce0" in devices
    assert "lo0" in devices


@mock.patch("cloudinit.net.util.is_FreeBSD", return_value=True)
def test_freebsd_azure_filters_hyperv_vf_when_synthetic_present(
    _is_freebsd, caplog
):
    """On Azure FreeBSD, accelerated VFs (mce*) must be ignored when a
    synthetic hn* interface with the same MAC is present.
    """
    caplog.set_level(logging.DEBUG)

    interfaces = [
        ("hn0", "aa:bb:cc:dd:ee:ff", "hn", ""),
        ("mce0", "aa:bb:cc:dd:ee:ff", "mce", ""),
    ]

    filtered = list(interfaces)

    net.filter_hyperv_vf_with_synthetic_interface(LOG.debug, filtered)

    names = [iface[0] for iface in filtered]

    assert "hn0" in names
    assert "mce0" not in names

    assert (
        "Ignoring 'mce0' VF interface due to synthetic hn interface 'hn0'"
        in caplog.text
    )


@mock.patch("cloudinit.net.util.is_FreeBSD", return_value=True)
@mock.patch("cloudinit.net.subp.subp")
@mock.patch("cloudinit.net.get_interfaces_by_mac")
def test_freebsd_prefers_hn0_as_primary_interface(
    m_get_by_mac, m_subp, _is_freebsd
):
    m_get_by_mac.return_value = {
        "aa:aa:aa:aa:aa:01": "mce0",
        "aa:aa:aa:aa:aa:02": "hn1",
        "aa:aa:aa:aa:aa:03": "hn0",
    }

    # Order returned by ifconfig -l -u ether
    m_subp.return_value = ("mce0 hn1 hn0", "")

    ordered = net.find_candidate_nics_on_freebsd()

    assert ordered[0] == "hn0"
