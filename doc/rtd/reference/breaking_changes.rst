.. _breaking_changes:

Breaking changes
****************

This section provides guidance on specific breaking changes to cloud-init
releases.

.. note::
    These changes may not be present in all distributions of cloud-init as
    many operating system vendors patch out breaking changes in
    cloud-init to ensure consistent behavior on their platform.

24.1
====

Removal of ``--file`` top-level option
--------------------------------------

The ``--file`` top-level option has been removed from cloud-init. It only
applied to a handful of subcommands so it did not make sense as a top-level
option. Instead, ``--file`` may be passed to a subcommand that supports it.
For example, the following command will no longer work:

.. code-block:: bash

    cloud-init --file=userdata.yaml modules --mode config

Instead, use:

.. code-block:: bash

    cloud-init modules --file=userdata.yaml --mode config


Removed Ubuntu's ordering dependency on snapd.seeded
----------------------------------------------------

In Ubuntu releases, cloud-init will no longer wait on ``snapd`` pre-seeding to
run. If a user-provided script relies on a snap, it must now be prefixed with
``snap wait system seed.loaded`` to ensure the snaps are ready for use. For
example, a cloud config that previously included:

.. code-block:: yaml

    runcmd:
      - [ snap, install, mc-installer ]


Will now need to be:

.. code-block:: yaml

    runcmd:
      - [ snap, wait, system, seed.loaded ]
      - [ snap, install, mc-installer ]


23.2-24.1 - Datasource identification
=====================================

**23.2**
    If the detected ``datasource_list`` contains a single datasource or
    that datasource plus ``None``, automatically use that datasource without
    checking to see if it is available. This allows for using datasources that
    don't have a way to be deterministically detected.
**23.4**
    If the detected ``datasource_list`` contains a single datasource plus
    ``None``, no longer automatically use that datasource because ``None`` is
    a valid datasource that may be used if the primary datasource is
    not available.
**24.1**
    ds-identify no longer automatically appends ``None`` to a
    datasource list with a single entry provided under ``/etc/cloud``.
    If ``None`` is desired as a fallback, it must be explicitly added to the
    customized datasource list.

23.4 - added status code for recoverable error
==============================================

Cloud-init return codes have been extended with a new error code (2),
which will be returned when cloud-init experiences an error that it can
recover from. See :ref:`this page which documents the change <error_codes>`.


23.2 - kernel command line
==========================

The ``ds=`` kernel command line value is used to forcibly select a specific
datasource in cloud-init. Prior to 23.2, this only optionally selected
the ``NoCloud`` datasource.

Anyone that previously had a matching ``ds=nocloud*`` in their kernel command
line that did not want to use the ``NoCloud`` datasource may experience broken
behavior as a result of this change.

Workarounds include updating the kernel command line and optionally configuring
a ``datasource_list`` in ``/etc/cloud/cloud.cfg.d/*.cfg``.
