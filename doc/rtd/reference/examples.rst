.. _yaml_examples:

All cloud config examples
*************************

.. note::
   This page is a summary containing all the cloud config YAML examples
   together. If you would like to explore examples by operation or process
   instead, refer to the :ref:`examples library <examples_library>`.

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

Configure an instance's trusted CA certificates
===============================================

.. literalinclude:: ../../examples/cloud-config-ca-certs.txt
   :language: yaml
   :linenos:

Install and run `chef`_ recipes
===============================

.. literalinclude:: ../../examples/cloud-config-chef.txt
   :language: yaml
   :linenos:

Install and run `ansible-pull`
===============================

.. literalinclude:: ../../examples/cloud-config-ansible-pull.txt
   :language: yaml
   :linenos:

Configure instance to be managed by Ansible
===========================================

.. literalinclude:: ../../examples/cloud-config-ansible-managed.txt
   :language: yaml
   :linenos:

Configure instance to be an Ansible controller
==============================================

.. literalinclude:: ../../examples/cloud-config-ansible-controller.txt
   :language: yaml
   :linenos:

Add primary apt repositories
============================

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

Run commands on very early at every boot
========================================

.. literalinclude:: ../../examples/boothook.txt
   :language: bash
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

Configure instance's SSH keys
=============================

.. literalinclude:: ../../examples/cloud-config-ssh-keys.txt
   :language: yaml
   :linenos:

Additional apt configuration and repositories
=============================================

.. literalinclude:: ../../examples/cloud-config-apt.txt
    :language: yaml
    :linenos:

Disk setup
==========

.. literalinclude:: ../../examples/cloud-config-disk-setup.txt
    :language: yaml
    :linenos:

Create partitions and filesystems
=================================

.. literalinclude:: ../../examples/cloud-config-disk-setup.txt
   :language: yaml
   :linenos:

.. _chef: http://www.chef.io/chef/
.. _puppet: http://puppetlabs.com/
.. _ansible: https://docs.ansible.com/ansible/latest/

