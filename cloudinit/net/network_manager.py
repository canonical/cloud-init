import logging
import os

from cloudinit import subp
from cloudinit import util
from cloudinit.net.activator import NetworkActivator

LOG = logging.getLogger(__name__)

NM_CFG_FILE = "/etc/NetworkManager/NetworkManager.conf"


class NetworkManagerActivator(NetworkActivator):
    @staticmethod
    def available(target=None) -> bool:
        config_present = os.path.isfile(
            subp.target_path(target, path=NM_CFG_FILE)
        )
        nmcli_present = subp.which('nmcli', target=target)
        return config_present and bool(nmcli_present)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        try:
            subp.subp(['nmcli', 'connection', 'up', device_name])
        except subp.ProcessExecutionError:
            util.logexc(LOG, "nmcli failed to bring up {}".format(device_name))
            return False
        return True
