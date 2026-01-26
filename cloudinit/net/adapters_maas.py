import logging
from typing import TYPE_CHECKING, Any, Dict

from cloudinit.net.adapters import NetworkingAdapter

if TYPE_CHECKING:
    from cloudinit.distros import Distro

LOG = logging.getLogger(__name__)


class MAASNetworkingAdapter(NetworkingAdapter):
    """
    MAAS-specific networking adapter.

    This preserves existing MAAS behavior but localizes it.
    """

    def render(
        self,
        network_config: Dict[str, Any],
        *,
        datasource: object,
        distro: "Distro",
    ) -> Dict[str, Any]:
        LOG.debug("MAAS adapter rendering network config")

        rendered = dict(network_config)

        ethernets = rendered.get("ethernets", {})
        for _, cfg in ethernets.items():
            if cfg.get("openvswitch"):
                cfg.setdefault("mtu", 1500)

        return rendered
