from cloudinit import subp, util


class Pip:
    @classmethod
    def install_packages(cls, pkglist: str):
        subp.subp(
            [
                "pip",
                "install",
                "--user",
                util.expand_package_list("%s==%s", pkglist),
            ]
        )
