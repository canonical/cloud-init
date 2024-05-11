.. _yaml_examples:

Cloud-config example library
****************************

These examples will help to illustrate how the cloud-init modules can be called
in the user data cloud-config file.

For more information about how this file should be constructed and how it
works, refer to our guide to the
:ref:`cloud-init config file <about-cloud-config>`.

Package management
==================

.. toctree::
   :maxdepth: 1

   yaml_examples/apt.rst
   yaml_examples/apt-repos.rst
   yaml_examples/apt-pipeline.rst
   yaml_examples/apk-repo.rst
   yaml_examples/yum-repo.rst
   yaml_examples/zypper-repo.rst
   yaml_examples/update-upgrade.rst

Configuration management
========================

.. toctree::
   :maxdepth: 1

   yaml_examples/ansible.rst
   yaml_examples/chef.rst
   yaml_examples/puppet.rst
   yaml_examples/salt-minion.rst

System initialization and boot
==============================

.. toctree::
   :maxdepth: 1

   yaml_examples/boot-cmds.rst
   yaml_examples/scripts.rst
   yaml_examples/byobu.rst
   yaml_examples/disk-setup.rst
   yaml_examples/fan.rst
   yaml_examples/grub-dpkg.rst
   yaml_examples/landscape.rst
   yaml_examples/seed-random.rst
   yaml_examples/set-hostname.rst
   yaml_examples/set-passwords.rst
   yaml_examples/ssh.rst
   yaml_examples/ssh-authkey-fingerprints.rst
   yaml_examples/ssh-import-id.rst

Networking
==========

.. toctree::
   :maxdepth: 1

   yaml_examples/ntp.rst
   yaml_examples/resolv-conf.rst
   yaml_examples/wireguard.rst
   yaml_examples/update-etc-hosts.rst
   yaml_examples/update-hostname.rst

User management
===============

.. toctree::
   :maxdepth: 1

   yaml_examples/user-groups.rst

File system management
======================

.. toctree::
   :maxdepth: 1

   yaml_examples/growpart.rst
   yaml_examples/mounts.rst
   yaml_examples/resizefs.rst
   yaml_examples/write-files.rst

System monitoring and logging
=============================

.. toctree::
   :maxdepth: 1

   yaml_examples/reporting.rst
   yaml_examples/final-message.rst
   yaml_examples/rsyslog.rst

Security
========

.. toctree::
   :maxdepth: 1

   yaml_examples/ca-certs.rst
   yaml_examples/disable-ec2-metadata.rst

Ubuntu
======

.. toctree::
   :maxdepth: 1

   yaml_examples/snap.rst
   yaml_examples/ubuntu-pro.rst
   yaml_examples/ubuntu-drivers.rst
   yaml_examples/landscape.rst

System configuration
====================

.. toctree::
   :maxdepth: 1

   yaml_examples/keyboard.rst
   yaml_examples/keys-to-console.rst
   yaml_examples/locale-and-timezone.rst

Miscellaneous
=============

.. toctree::
   :maxdepth: 1

   yaml_examples/lxd.rst
   yaml_examples/install-hotplug.rst
   yaml_examples/mcollective.rst
   yaml_examples/phone-home.rst
   yaml_examples/power-state-change.rst
   yaml_examples/spacewalk.rst

Datasources
===========

.. toctree::
   :maxdepth: 1

   yaml_examples/datasources.rst
   yaml_examples/redhat-subscription.rst


Complex examples
================

.. toctree::
   :maxdepth: 1

   yaml_examples/archive.rst
   yaml_examples/archive-launch-index.rst
   yaml_examples/launch-index.rst
   yaml_examples/gluster.rst
   yaml_examples/ansible-pull.rst
   yaml_examples/ansible-managed.rst
   yaml_examples/ansible-controller.rst
