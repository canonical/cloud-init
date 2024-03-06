Supported distros
=================

Cloud-init has support for multiple different operating systems.
Currently support includes various different distributions within the
Unix family of operating systems. See the complete list below.

* AlmaLinux
* Alpine Linux
* Arch Linux
* CentOS
* CloudLinux
* Container-Optimized OS
* Debian
* DragonFlyBSD
* EuroLinux
* Fedora
* FreeBSD
* Gentoo
* MarinerOS
* MIRACLE LINUX
* NetBSD
* OpenBSD
* openEuler
* OpenCloudOS
* OpenMandriva
* PhotonOS
* Red Hat Enterprise Linux
* Rocky
* SLES/openSUSE
* TencentOS
* Ubuntu
* Virtuozzo

If you would like to add support for another distributions, start by
taking a look at another distro module in ``cloudinit/distros/``.

.. note::

    While BSD variants are not typically referred to as "distributions",
    cloud-init has an abstraction to account for operating system differences, which
    should be contained in `cloudinit/distros/ <https://github.com/canonical/cloud-init/tree/main/cloudinit/distros>`_.
