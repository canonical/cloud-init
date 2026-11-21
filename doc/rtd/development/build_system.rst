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

.. code-block:: shell-session

   ./tools/read-dependencies --requirements-file requirements.txt --requirements-file test-requirements.txt --system-pkg-names --system-pkg-names --distro=<your_distro_name>


Manual build procedure
----------------------

Meson install directory locations may be set with
``meson setup -D<option_name>=<option_value>``. See :file:`meson_options.txt`
for available build options.

The systemd generator uses the same helper directory as Meson's
installation rules: ``<prefix>/<libexecdir>/cloud-init``. An absolute
``libexecdir`` overrides the prefix. For example,
``--prefix=/usr --libexecdir=libexec`` installs ``ds-identify`` at
``/usr/libexec/cloud-init/ds-identify`` and embeds that path in the
generator. When rendering the generator directly with
``tools/render-template``, pass ``--lib-exec-dir`` with the full helper
directory to override the distribution-specific default.

Meson also records this directory in the installed
``cloudinit/meson_paths.py``. The SSH host-key console module and the
executable temporary-directory fallback use this value, including custom
prefixes and absolute ``libexecdir`` settings. Reconfiguring Meson updates
both the generator and Python paths. Staging with ``DESTDIR`` does not
change these runtime paths. Source checkouts without generated metadata
continue to use the distribution's default directory.

Steps to validate ``cloud-init`` package builds in a development environment:

.. code-block:: bash

   meson setup builddir -Dsystemd -Ddownstream_version=X.Y.Z
   meson test -C builddir -v
   meson install -C builddir
   # List installed files
   find builddir/testinstall/

.. LINKS:
.. _meson: https://mesonbuild.com/
