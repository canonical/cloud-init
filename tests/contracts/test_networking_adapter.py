from cloudinit.net.adapters import NetworkingAdapter
from cloudinit.net.adapters_maas import MAASNetworkingAdapter

def test_maas_adapter_contract():
    adapter = MAASNetworkingAdapter()
    # Check it's a NetworkingAdapter subclass
    assert isinstance(adapter, NetworkingAdapter)
    # Check render exists
    assert callable(adapter.render)
