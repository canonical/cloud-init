.. _packaging:

Packaging
*********

``Cloud-init`` is packaged as a system package by image creators and
typically included in base cloud images. It is packaged as
distribution-specific downstream binaries which are pre-installed in cloud
images because ``cloud-init`` delivers system initialization services for early
boot configuration.

The build system used by ``cloud-init`` is `meson`_. ``Cloud-init`` is not
published to pypi.org because it is not intended to be consumed directly as a
pure-python library, SDK or API for managing cloud configuration.

``Cloud-init`` correct behavior depends on the tight integration of
system services performing :ref:`the early boot stages<boot_stages>` and
system-wide configuration. Upstream uses `meson`_ build backend to support the
distribution of all dependent data files, system-initialization scripts and
global configuration files.

Guidelines
==========

Below is a list of guidelines for downstream cloud-init package maintainers

Build Dependencies
------------------
To use ``meson```, the following build dependencies should be available on the
system:
- ``python3``
- ``meson >= 0.63.0``
- ``pkgcfg``
- ``bash-completion``
- ``systemd-devel`` For systemd environments
- ``udev```  For systemd environments

Local build procedure
---------------------

There are two custom meson build options used by the ``cloud-init`` project.
They are ``init_system`` and ``readthedocs_build``. The ``readthedocs_build``
boolean defaults to ``false`` in :file:`meson_options.txt` and limits the
dependencies used by :file:`meson.build`. It should only be ``true`` during
RTD builds as it limits build dependencies expected by :file:`meson.build`.

The ``init_system`` option affect paths where init scripts, configuration
files, executables and data files are installed. The ``init_system`` value
defaults to ``systemd``.

Steps to validate ``cloud-init`` package builds in a development environment:

.. code-block:: bash

   meson setup ../builddir -Dinit_system=systemd
   meson compile -C ../builddir
   meson test -C ../builddir -v


Downstream package builds
-------------------------

In some distributions, the previous build procedure has built-in meson support
in various package build tools. Both Debian and Redhat have builtin helpers or
build macros tooling support meson-based projects.

On DEB-based systems, debhelper's meson plugin auto-detects the meson
project build system by the presence of a meson.build file in the project
root directory. But, debian/rules can pass the specific build system override
to debhelper:

.. code-block:: bash

   # debian/rules
   %:
           dh $@ --buildsystem meson
   override_dh_auto_configure:
           dh_auto_configure -- -Dinit_system=systemd -Dlibexecdir=lib -Dudevdir=/usr/lib/udev


   # debian/control
   Build-Depends: meson,
                  pkgcfg,
                  bash-completion,
                  systemd-dev,
                  udev,
                  ...


On RPM-based systems, rpmbuild has a number or
`spec file meson-related macros`_. But, general spec files should invoke
something like the following:

.. code-block: bash

   %build
   %meson -Dinit_system=systemd
   %meson_build
   ...
   %install
   %meson_install

   %check
   %meson_test


One should first look to official downstream pre-built packages of
``cloud-init`` for your prefered operating system. But, for those interested
in package build development examples, spec templates and debian/rules or
control files are provided as a development examples at:
- `SUSE RPM spec template`_
- `RedHat RPM spec template`_
- `Debian DEB rules template`_
- Ubuntu downstream: `debian/rules`_ and `debian/control`_


Those templates can be used to build development-quality RPM or DEB packages:

.. code-block:: bash

   ./packages/brpm --distro=redhat   # or --distro=suse
   ./packages/bdeb --distro=ubuntu   # or --distro=debian

OR if LXC is available:

.. code-block:: bash

   ./tools/run-container ubuntu-daily:plucky --package --keep
   ./tools/run-container rockylinux/9 --package --keep


.. note::

   FreeBSD, NetBSD and OpenBSD meson support has not yet been added to :file:`tools/build-on-*bsd` or :file:`meson.build`.


.. LINKS:
.. _meson: https://mesonbuild.com/
.. _debhelper's meson plugin: https://github.com/Debian/debhelper/blob/master/lib/Debian/Debhelper/Buildsystem/meson.pm
.. _spec file meson-related macros: https://docs.fedoraproject.org/en-US/packaging-guidelines/Meson/
.. _RedHat RPM spec template:  https://github.com/canonical/cloud-init/blob/main/packages/redhat/cloud-init.spec.in
.. _SUSE RPM spec template:  https://github.com/canonical/cloud-init/blob/main/packages/suse/cloud-init.spec.in
.. _Debian DEB rules template:  https://github.com/canonical/cloud-init/blob/main/packages/debian/rules
.. _debian/rules:  https://github.com/canonical/cloud-init/tree/ubuntu/devel/debian/rules
.. _debian/control:  https://github.com/canonical/cloud-init/tree/ubuntu/devel/debian/control
