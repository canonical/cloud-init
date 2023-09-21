from cloudinit.distros.package_management.apt import Apt
from cloudinit.distros.package_management.snap import Snap


known_package_managers = {
    "apt": Apt,
    "snap": Snap,
}
