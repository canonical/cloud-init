.. _cce-yum-repo:

Yum repositories
****************

This example shows how to configure a ``yum`` repository. For a full list of
keys, refer to the `yum add repo module`_ schema.

Add a yum repo (basic example)
==============================

.. code-block:: yaml

    #cloud-config
    yum_repos:
      my_repo:
        baseurl: http://blah.org/pub/epel/testing/5/$basearch/
    yum_repo_dir: /store/custom/yum.repos.d

Add daily testing repo
======================

This example enables cloud-init upstream's daily testing repo for EPEL 8 to
install the latest version of cloud-init from tip of ``main`` for testing.

.. code-block:: yaml

    #cloud-config
    yum_repos:
      cloud-init-daily:
        name: Copr repo for cloud-init-dev owned by @cloud-init
        baseurl: https://download.copr.fedorainfracloud.org/results/@cloud-init/cloud-init-dev/epel-8-$basearch/
        type: rpm-md
        skip_if_unavailable: true
        gpgcheck: true
        gpgkey: https://download.copr.fedorainfracloud.org/results/@cloud-init/cloud-init-dev/pubkey.gpg
        enabled_metadata: 1

Add EPEL testing repo
=====================

The following example adds the ``/etc/yum.repos.d/epel_testing.repo`` file,
which can be subsequently used by ``yum`` for later operations.

.. code-block:: yaml

    #cloud-config
    yum_repos:
      epel-testing:
        baseurl: https://download.copr.fedorainfracloud.org/results/@cloud-init/cloud-init-dev/pubkey.gpg
        enabled: false
        failovermethod: priority
        gpgcheck: true
        gpgkey: file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL
        name: Extra Packages for Enterprise Linux 5 - Testing

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
created.

This example will write ``/etc/yum.conf.d/my-package-stream.repo``, with GPG
key checks on the repo data of the enabled repository.

.. code-block:: yaml

    #cloud-config
    yum_repos:
      my package stream:
        baseurl: http://blah.org/pub/epel/testing/5/$basearch/
        mirrorlist: http://some-url-to-list-of-baseurls
        repo_gpgcheck: 1
        enable_gpgcheck: true
        gpgkey: https://url.to.ascii-armored-gpg-key


.. LINKS
.. _yum add repo module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#yum-add-repo

