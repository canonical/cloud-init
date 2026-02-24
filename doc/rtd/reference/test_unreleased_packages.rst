.. _ubuntu_test_unreleased_packages:

Test Unreleased Packages
************************

Testing a pre-built package is the easiest way to test the latest code.
Pre-release packages and daily packages are two ways to accomplish this before
it becomes available in official distro repositories and cloud images.

If you must modify the code locally, you will need to build from source
instead.

.. _ubuntu_test_pre_release:

Test pre-release packages
=========================

After the cloud-init team creates an upstream release, cloud-init will
be released in the -proposed APT repository for a
:ref:`period of testing<sru_testing>` which provides
:ref:`SRU updates to multiple Ubuntu releases<sru_supported_releases>`. Users
are encouraged to test their workloads on pending releases so bugs can be
caught and fixed prior to becoming more broadly available via the -updates
repository. This guide describes how to test the pre-release package on Ubuntu.

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

If issues are found during testing, please file a
:ref:`new cloud-init bug<reporting_bugs>`.

Remove the proposed repository
------------------------------

Do this to avoid unintentionally installing other unreleased packages.

.. code-block:: bash

    rm /etc/apt/sources.list.d/proposed.list
    apt update

Remove artifacts and reboot
---------------------------

This will cause cloud-init to rerun as if it is a first boot.

.. code-block:: bash

    sudo cloud-init clean --logs --reboot

Test daily packages
===================

Daily builds allow one to test the latest upstream code for the newest features
and bug fixes without building from source.

For Ubuntu, install from the `Daily PPA`_.

For CentOS, install from `COPR`_.

.. _Daily PPA: https://code.launchpad.net/~cloud-init-dev/+archive/ubuntu/daily
.. _COPR: https://copr.fedorainfracloud.org/coprs/g/cloud-init/cloud-init-dev/
