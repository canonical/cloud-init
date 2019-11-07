# Cloud-init official project upstream as of 11/2019
This repository is also mirrored to https://launchpad.net/cloud-init

[![Build Status](https://travis-ci.org/canonical/cloud-init.svg?branch=master)](https://travis-ci.org/canonical/cloud-init) [![Read the Docs](https://readthedocs.org/projects/cloudinit/badge/?version=latest&style=flat)](https://cloudinit.readthedocs.org)

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all
major public cloud providers, provisioning systems for private cloud
infrastructure, and bare-metal installations.

Cloud instances are initialized from a disk image and instance data:

- Cloud metadata
- User data (optional)
- Vendor data (optional)

Cloud-init will identify the cloud it is running on during boot, read any
provided metadata from the cloud and initialize the system accordingly. This
may involve setting up the network and storage devices to configuring SSH
access key and many other aspects of a system. Later on the cloud-init will
also parse and process any optional user or vendor data that was passed to the
instance.

## Getting involved
All contributions welcome! [Submit code and docs by following our hacking guide](https://cloudinit.readthedocs.io/en/latest/topics/hacking.html)

## Getting help

Having trouble? We would like to help!

- Ask a question in the [``#cloud-init`` IRC channel on Freenode](https://webchat.freenode.net/?channel=#cloud-init)
- Join and ask questions on the [cloud-init mailing list](https://launchpad.net/~cloud-init)
- Find a bug? [Report bugs on Launchpad](https://bugs.launchpad.net/cloud-init)

## Recent cloud-init upstream releases
Upstream release version | Release date |
---   | ---  |
19.4 | planned (2019-12-XX) |
[19.3](https://launchpad.net/cloud-init/+milestone/19.3)  | 2019-11-05 |
[19.2](https://launchpad.net/cloud-init/+milestone/19.2)  | 2019-07-17 |
[19.1](https://launchpad.net/cloud-init/+milestone/19.1)  | 2019-05-10 |


## Cloud-init distribution and cloud support
Note: Each linux distribution and cloud tracks cloud-init upstream updates at
a different pace. If your distribution or cloud doesn't contain a recent
cloud-init, suggest or propose an upgrade with your distribution of choice.

| Supported OSes | Supported Public Clouds | Supported Private Clouds |
| --- | --- | --- |
| Ubuntu<br />SLES/openSUSE<br />RHEL/CentOS<br />Fedora<br />Gentoo Linux<br />Debian<br />ArchLinux<br />FreeBSD<br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /> | Amazon Web Services<br />Microsoft Azure<br />Google Cloud Platform<br />Oracle Cloud Infrastructure<br />Softlayer<br />Rackspace Public Cloud<br />IBM Cloud<br />Digital Ocean<br />Bigstep<br />Hetzner<br />Joyent<br />CloudSigma<br />Alibaba Cloud<br />OVH<br />OpenNebula<br />Exoscale<br />Scaleway<br />CloudStack<br />AltCloud<br />SmartOS<br /> | Bare metal installs<br />OpenStack<br />LXD<br />KVM<br />Metal-as-a-Service (MAAS)<br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br /><br />|


## Daily Package Builds
We host daily [Ubuntu Daily PPAs](https://code.launchpad.net/~cloud-init-dev/+recipes) that build package for each Ubuntu series from tip of cloud-init.

For CentOS 7/8 we publish to a couple of COPR build repos:

 * [**cloud-init-dev**: daily builds from cloud-init tip](https://copr.fedorainfracloud.org/coprs/g/cloud-init/cloud-init-dev/)

