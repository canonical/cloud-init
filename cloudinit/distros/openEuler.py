from cloudinit.distros import rhel
from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class Distro(rhel.Distro):
    pass

# vi: ts=4 expandtab
