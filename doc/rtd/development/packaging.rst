.. _downstream_packaging:

Downstream packaging
********************

This page is intended to support operating system packagers of ``cloud-init``
and is not intended for other audiences to generate their own custom cloud-init
packages.

``Cloud-init`` is not published to PyPI as it is not intended to be consumed
as a pure-python package or run from virtual environments or python paths that
are not system-wide.

Guidelines
==========

Build Dependencies
------------------
The following build dependencies must be available on the system:

- ``python3``
- ``meson >= 0.63.0``
- ``pkgconf``
- ``bash-completion``

Additional dependencies for systemd environments:

- ``systemd-devel``
- ``udev``

The full list of all package build-dependencies for a given
distribution can be obtained by the following command:

.. code-block:: bash

   ./tools/read-dependencies --system --distro=<your_distro_name>


Manual build procedure
----------------------

Meson install directory locations may be set with
``meson setup -D<option_name>=<option_value>``.

Steps to validate ``cloud-init`` package builds in a development environment:

.. code-block:: bash

   meson setup builddir
   meson test -C builddir -v
   meson install -C builddir --destdir=testinstall
   # List installed files
   find builddir/testinstall/


Test builds of RPMs or DEBs
---------------------------
To ease the development and testing of local changes, development-quality DEB
or RPM packages can be built with one of the following scripts on a build host
which already has all system build dependencies installed:

.. code-block:: bash

   ./packages/brpm --distro=redhat  # or --distro=suse to build an RPM
   ./packages/bddeb -d  # to build a DEB

OR if LXC is present, the full package build can be run in a container:

.. code-block:: bash

   ./tools/run-container ubuntu-daily:plucky --package --keep
   ./tools/run-container rockylinux/9 --package --keep


.. note::

   meson support has not yet been added to the BSDs in :file:`tools/build-on-*bsd` or :file:`meson.build`.


.. LINKS:
.. _meson: https://mesonbuild.com/
