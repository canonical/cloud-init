from cloudinit.net.adapters_maas import MAASNetworkingAdapter


def test_maas_ovs_interface_preserved():
    adapter = MAASNetworkingAdapter()

    cfg = {
        "version": 2,
        "ethernets": {
            "eno1": {
                "openvswitch": True,
                "addresses": ["192.168.1.10/24"],
            }
        },
    }

    rendered = adapter.render(cfg, datasource=None, distro=None)

    assert rendered["ethernets"]["eno1"]["mtu"] == 1500
