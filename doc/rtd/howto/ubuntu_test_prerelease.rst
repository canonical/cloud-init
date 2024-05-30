.. _ubuntu_test_pre_release:

Test pre-release cloud-init
===========================

After the cloud-init team creates an upstream release, cloud-init will
be released in the -proposed APT repository for a
:ref:`period of testing<sru_testing>`. Users are encouraged to test their
workloads on this pending release so that bugs can be caught and fixed prior
to becoming more broadly available via the -updates repository. This guide
describes how to test the pre-release package on Ubuntu.

Add the -proposed repository pocket
-----------------------------------

The -proposed repository pocket will contain the cloud-init package to be
tested prior to release in the -updates pocket.

.. code-block:: bash

    echo "deb http://archive.ubuntu.com/ubuntu $(lsb_release -sc)-proposed main" >> /etc/apt/sources.list.d/proposed.list
    apt update

Install the pre-release cloud-init package
------------------------------------------

.. code-block:: bash

    apt install cloud-init

Test the package
----------------

Whatever workload you use cloud-init for in production is the best one
to test. This ensures that you can discover and report any bugs that the
cloud-init developers missed during testing before cloud-init gets
released more broadly.

If issues are found during testing, please file a `new cloud-init bug`_ and
leave a message in the `#cloud-init IRC channel`_.

Remove the proposed repository
------------------------------

Do this to avoid unintentionally installing other unreleased packages.

.. code-block:: bash

    rm -f /etc/apt/sources.list.d/proposed.list
    apt update

Remove artifacts and reboot
---------------------------

This will cause cloud-init to rerun as if it is a first boot.

.. code-block:: bash

    sudo cloud-init clean --logs --reboot

.. _new cloud-init bug: https://github.com/canonical/cloud-init/issues
.. _#cloud-init IRC channel: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
