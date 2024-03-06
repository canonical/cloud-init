from typing import Dict, Type

from cloudinit.distros.package_management.apt import Apt
from cloudinit.distros.package_management.package_manager import PackageManager
from cloudinit.distros.package_management.snap import Snap

known_package_managers: Dict[str, Type[PackageManager]] = {
    "apt": Apt,
    "snap": Snap,
}
