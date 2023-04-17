# packages

Package builders under this folder are development only templates. Do not rely on them.

## Build/Install

Cloud-init's build/install procedure is not OS/Distro independent as cloud-init
is tightly couple to OS implementation details, as for example,
the init units' definitions, see [systemd/](systemd/) and [sysvinit/](sysvinit/).

For users interested in trying out cloud-init, a pre-built image is the easiest option.

For users interested in packaging cloud-init, see the reference implementations under this folder
and official packages in the following section.

## Downstream packaging resources

* [arch](https://archlinux.org/packages/community/any/cloud-init/)
* [alpine](https://pkgs.alpinelinux.org/packages?name=cloud-init)
* [debian](https://packages.debian.org/sid/cloud-init)
* [fedora](https://src.fedoraproject.org/rpms/cloud-init)
* [freebsd](https://www.freshports.org/net/cloud-init/) [devel package](https://www.freshports.org/net/cloud-init-devel)
* [gentoo](https://packages.gentoo.org/packages/app-emulation/cloud-init)
* [opensuse](https://build.opensuse.org/package/show/Cloud:Tools/cloud-init)
* [ubuntu](https://launchpad.net/cloud-init)
