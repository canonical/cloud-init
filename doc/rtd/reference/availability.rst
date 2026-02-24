.. _availability:

Availability
************

Below outlines the current availability of ``cloud-init`` across
distributions and clouds, both public and private.

.. note::

    If a distribution or cloud does not show up in the list below, contact
    them and ask for images to be generated using ``cloud-init``!

Distributions
=============

``Cloud-init`` has support across all major Linux distributions, FreeBSD,
NetBSD, OpenBSD and DragonFlyBSD:

- AlmaLinux
- Alpine Linux
- AOSC OS
- Amazon Linux 2023
- Arch Linux
- CentOS
- CloudLinux
- Container-Optimized OS
- Debian
- DragonFlyBSD
- EuroLinux
- Fedora
- FreeBSD
- Gentoo Linux
- MarinerOS
- MIRACLE LINUX
- NetBSD
- OpenBSD
- openEuler
- OpenCloudOS
- OpenMandriva
- Photon OS
- Raspberry Pi OS
- Red Hat Enterprise Linux (RHEL)
- Rocky Linux
- SLES/openSUSE
- TencentOS
- Ubuntu
- Virtuozzo

.. note::

    While BSD variants are not typically referred to as "distributions",
    ``cloud-init`` has an abstraction to account for operating system differences,
    which can be found in the `cloudinit/distros/ <https://github.com/canonical/cloud-init/tree/main/cloudinit/distros>`_ directory.

Clouds
======

``Cloud-init`` provides support across a wide-ranging list of execution
environments in the public cloud:

- Amazon Web Services
- Microsoft Azure
- Google Cloud Platform
- Oracle Cloud Infrastructure
- Softlayer
- Rackspace Public Cloud
- IBM Cloud
- DigitalOcean
- Bigstep
- Hetzner
- Joyent
- CloudSigma
- Alibaba Cloud
- OVH
- OpenNebula
- Exoscale
- Scaleway
- CloudStack
- AltCloud
- SmartOS
- UpCloud
- Vultr
- Zadara Edge Cloud Platform
- 3DS Outscale
- Akamai

Additionally, ``cloud-init`` is supported on these private clouds:

- Bare metal installs
- OpenStack
- LXD
- KVM
- Metal-as-a-Service (MAAS)
- VMware
