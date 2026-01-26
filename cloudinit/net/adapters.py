from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from cloudinit.distros import Distro


class NetworkingAdapter(ABC):
    """
    Contract for platform-specific networking behavior.

    Implementations must be deterministic and idempotent.
    """

    @abstractmethod
    def render(
        self,
        network_config: Dict[str, Any],
        *,
        datasource: object,
        distro: "Distro",
    ) -> Dict[str, Any]:
        """
        Transform cloud-init network config into an OS-specific
        rendered representation (e.g. netplan dict).
        """
        raise NotImplementedError
