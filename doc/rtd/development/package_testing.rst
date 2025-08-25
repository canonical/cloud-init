.. _package_testing:

Development package builds
**************************

To ease the development and testing of local packaging changes,
development-quality DEB or RPM packages can be built with one of the following
scripts on a build host which already has all system build dependencies
installed:

.. code-block:: bash

   ./packages/brpm --distro=redhat  # or --distro=suse to build an RPM
   ./packages/bddeb -d  # to build a DEB

OR if LXD is present, the full package build can be run in a container:

.. code-block:: bash

   ./tools/run-container ubuntu-daily:plucky --package --keep
   ./tools/run-container rockylinux/9 --package --keep


.. note::

   meson support has not yet been added to the BSDs in :file:`tools/build-on-*bsd` or :file:`meson.build`.
