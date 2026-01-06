from cloudinit.net.network_state import NetworkStateInterpreter

def test_interface_with_default_route_is_preferred():
    config = {
        "version": 2,
        "ethernets": {
            "eth0": {
                "match": {"macaddress": "aa:bb:cc:dd:ee:01"},
                "dhcp4": True,
            },
            "eth1": {
                "match": {"macaddress": "aa:bb:cc:dd:ee:02"},
                "addresses": ["10.0.0.2/24"],
                "routes": [
                    {"to": "0.0.0.0/0", "via": "10.0.0.1"}
                ],
            },
        },
    }

    nsi = NetworkStateInterpreter(version=2, config=config)
    nsi.parse_config()
    state = nsi.network_state

    assert "eth1" in state._network_state["interfaces"]
    iface = state._network_state["interfaces"]["eth1"]

    # eth1 must be selected because it has default route
    assert iface["name"] == "eth1"



def test_single_interface_resolution_unchanged():
    config = {
        "version": 2,
        "ethernets": {
            "eth0": {
                "dhcp4": True,
            }
        },
    }

    nsi = NetworkStateInterpreter(version=2, config=config)
    nsi.parse_config()
    state = nsi.network_state

    assert "eth0" in state._network_state["interfaces"]



def test_deterministic_fallback_without_routes():
    config = {
        "version": 2,
        "ethernets": {
            "eth9": {"dhcp4": True},
            "eth1": {"dhcp4": True},
        },
    }

    nsi = NetworkStateInterpreter(version=2, config=config)
    nsi.parse_config()
    state = nsi.network_state

    # eth1 should win deterministically
    assert "eth1" in state._network_state["interfaces"]
