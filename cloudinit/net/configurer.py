# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC, abstractmethod
from typing import Iterable

from cloudinit.net.network_state import NetworkState


class NetworkConfigurer(ABC):
    @staticmethod
    @abstractmethod
    def available() -> bool:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def bring_up_interface(device_name: str) -> bool:
        raise NotImplementedError()

    @classmethod
    def bring_up_interfaces(cls, device_names: Iterable[str]) -> bool:
        all_succeeded = True
        for device in device_names:
            if not cls.bring_up_interface(device):
                all_succeeded = False
        return all_succeeded

    @classmethod
    def bring_up_all_interfaces(cls, network_state: NetworkState) -> bool:
        return cls.bring_up_interfaces(
            [i['name'] for i in network_state.iter_interfaces()]
        )
