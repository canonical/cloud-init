Build a distro package from source
**********************************

:ref:`Testing a pre-built package<ubuntu_test_unreleased_packages>` is the
easiest way to test the latest code. If you need to build a package with
custom changes to the code, some tools might help with building the package.

Development-quality DEB or RPM packages can be built from source with one of
the following scripts on a build host. Make sure that all dependencies are
installed:

.. code-block:: bash

   ./packages/brpm --distro=redhat  # or --distro=suse to build an RPM
   ./packages/bddeb -d  # to build a DEB

Alternatively the package can be built in an LXD container:

.. code-block:: bash

   ./tools/run-container ubuntu-daily:plucky --package --keep
   ./tools/run-container rockylinux/9 --package --keep

FreeBSD users might want to use :file:`tools/build-on-freebsd`.

See the `README`_ for more details.

.. _README: https://github.com/canonical/cloud-init/tree/main/packages
