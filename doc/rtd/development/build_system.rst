.. _build_system:

Build system
************

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

The full list of all package build dependencies for a given distribution can
be obtained by the following command:

.. code-block:: bash

   ./tools/read-dependencies --requirements-file requirements.txt --requirements-file test-requirements.txt --system-pkg-names --system-pkg-names --distro=<your_distro_name>


Manual build procedure
----------------------

Meson install directory locations may be set with
``meson setup -D<option_name>=<option_value>``. See :file:`meson_options.txt`
for available build options.

Steps to validate ``cloud-init`` package builds in a development environment:

.. code-block:: bash

   meson setup builddir -Dsystemd -Ddownstream_version=X.Y.Z
   meson test -C builddir -v
   meson install -C builddir
   # List installed files
   find builddir/testinstall/

.. LINKS:
.. _meson: https://mesonbuild.com/
