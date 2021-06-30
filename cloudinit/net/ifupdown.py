import logging

from cloudinit import subp
from cloudinit import util
from cloudinit.net.activator import NetworkActivator
from cloudinit.net.eni import available as eni_available

LOG = logging.getLogger(__name__)


class IfUpDownActivator(NetworkActivator):
    # Note that we're not overriding bring_up_interfaces to pass something
    # like ifup --all because it isn't supported everywhere.
    # E.g., NetworkManager has a ifupdown plugin that requires the name
    # of a specific connection.
    @staticmethod
    def available(target=None) -> bool:
        """Return true if ifupdown can be used on this system."""
        return eni_available(target=target)

    @staticmethod
    def bring_up_interface(device_name: str) -> bool:
        """Bring up interface using ifup."""
        cmd = ['ifup', device_name]
        LOG.debug("Attempting to run bring up interface %s using command %s",
                  device_name, cmd)
        try:
            (_out, err) = subp.subp(cmd)
            if len(err):
                LOG.warning("Running %s resulted in stderr output: %s",
                            cmd, err)
            return True
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False
