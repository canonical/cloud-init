.. _cce-yum-repo:

Yum repositories
****************

This example shows how to configure a ``yum`` repository. For a full list of
keys, refer to the :ref:`yum add repo module <mod_cc_yum_add_repo>` schema.

Add a yum repo (basic example)
==============================

.. literalinclude:: ../../../module-docs/cc_yum_add_repo/example1.yaml
   :language: yaml
   :linenos:

Add daily testing repo
======================

This example enables cloud-init upstream's daily testing repo for EPEL 8 to
install the latest version of cloud-init from tip of ``main`` for testing.

.. literalinclude:: ../../../module-docs/cc_yum_add_repo/example2.yaml
   :language: yaml
   :linenos:

Add EPEL testing repo
=====================

The following example adds the ``/etc/yum.repos.d/epel_testing.repo`` file,
which can be subsequently used by ``yum`` for later operations.

.. literalinclude:: ../../../module-docs/cc_yum_add_repo/example3.yaml
   :language: yaml
   :linenos:

Upgrade ``yum`` on boot
=======================

This example will upgrade the ``yum`` repository on first boot. The default
is ``false``.

.. code-block:: yaml

    #cloud-config
    package_upgrade: true

Configure a yum repo
====================

Any ``yum`` repo configuration can be passed directly into the repository file
created. See ``man yum.conf`` for supported config keys.

This example will write ``/etc/yum.conf.d/my-package-stream.repo``, with
``gpgkey`` checks on the repo data of the enabled repository.

.. literalinclude:: ../../../module-docs/cc_yum_add_repo/example4.yaml
   :language: yaml
   :linenos:

