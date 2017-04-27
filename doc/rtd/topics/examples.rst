.. _yaml_examples:

*********************
Cloud config examples
*********************

Including users and groups
==========================

.. literalinclude:: ../../examples/cloud-config-user-groups.txt
   :language: yaml
   :linenos:


Writing out arbitrary files
===========================

.. literalinclude:: ../../examples/cloud-config-write-files.txt
   :language: yaml
   :linenos:


Adding a yum repository
=======================

.. literalinclude:: ../../examples/cloud-config-yum-repo.txt
   :language: yaml
   :linenos:

Configure an instances trusted CA certificates
==============================================

.. literalinclude:: ../../examples/cloud-config-ca-certs.txt
   :language: yaml
   :linenos:

Configure an instances resolv.conf
==================================

*Note:* when using a config drive and a RHEL like system resolv.conf
will also be managed 'automatically' due to the available information
provided for dns servers in the config drive network format. For those
that wish to have different settings use this module.

.. literalinclude:: ../../examples/cloud-config-resolv-conf.txt
   :language: yaml
   :linenos:

Install and run `chef`_ recipes
===============================

.. literalinclude:: ../../examples/cloud-config-chef.txt
   :language: yaml
   :linenos:

Setup and run `puppet`_
=======================

.. literalinclude:: ../../examples/cloud-config-puppet.txt
   :language: yaml
   :linenos:

Add apt repositories
====================

.. literalinclude:: ../../examples/cloud-config-add-apt-repos.txt
   :language: yaml
   :linenos:

Run commands on first boot
==========================

.. literalinclude:: ../../examples/cloud-config-boot-cmds.txt
   :language: yaml
   :linenos:

.. literalinclude:: ../../examples/cloud-config-run-cmds.txt
   :language: yaml
   :linenos:


Alter the completion message
============================

.. literalinclude:: ../../examples/cloud-config-final-message.txt
   :language: yaml
   :linenos:

Install arbitrary packages
==========================

.. literalinclude:: ../../examples/cloud-config-install-packages.txt
   :language: yaml
   :linenos:

Update apt database on first boot
=================================

.. literalinclude:: ../../examples/cloud-config-update-apt.txt
   :language: yaml
   :linenos:

Run apt or yum upgrade
======================

.. literalinclude:: ../../examples/cloud-config-update-packages.txt
   :language: yaml
   :linenos:

Adjust mount points mounted
===========================

.. literalinclude:: ../../examples/cloud-config-mount-points.txt
   :language: yaml
   :linenos:

Call a url when finished
========================

.. literalinclude:: ../../examples/cloud-config-phone-home.txt
   :language: yaml
   :linenos:

Reboot/poweroff when finished
=============================

.. literalinclude:: ../../examples/cloud-config-power-state.txt
   :language: yaml
   :linenos:

Configure instances ssh-keys
============================

.. literalinclude:: ../../examples/cloud-config-ssh-keys.txt
   :language: yaml
   :linenos:
   
Additional apt configuration
============================

.. literalinclude:: ../../examples/cloud-config-apt.txt
    :language: yaml
    :linenos:

Disk setup
==========

.. literalinclude:: ../../examples/cloud-config-disk-setup.txt
    :language: yaml
    :linenos:

Register RedHat Subscription
============================

.. literalinclude:: ../../examples/cloud-config-rh_subscription.txt
    :language: yaml
    :linenos:

Configure data sources
======================

.. literalinclude:: ../../examples/cloud-config-datasources.txt
   :language: yaml
   :linenos:

Create partitions and filesystems
=================================

.. literalinclude:: ../../examples/cloud-config-disk-setup.txt
   :language: yaml
   :linenos:

Grow partitions
===============

.. literalinclude:: ../../examples/cloud-config-growpart.txt
   :language: yaml
   :linenos:

.. _chef: http://www.chef.io/chef/
.. _puppet: http://puppetlabs.com/
.. vi: textwidth=78
