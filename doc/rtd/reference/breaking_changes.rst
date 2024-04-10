.. _breaking_changes:

Breaking changes
****************

This section provides reference and guidance on specific breaking changes to 
cloud-init releases. 

24.1 - removed Ubuntu's ordering dependency on snapd.seeded
===========================================================

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


23.4 - added status code for recoverable error
==============================================

Cloud-init return codes have been extended with a new error code (2),
which will be returned when cloud-init experiences an error that it can
recover from.  See :ref:`this page which documents the change<error_codes>`.


23.2 - kernel commandline
=========================

The ds= kernel commandline value is used to forcibly select a specific
datasource in cloud-init. Prior to 23.2, this only optionally selected
the ``NoCloud`` datasource.

Anyone that previously had a matching `ds=nocloud*` in their kernel commandline
that did not want to use the NoCloud datasource may experience broken behavior
as a result of this change.

Workarounds include updating the kernel commandline and optionally configuring
a datasource_list in /etc/cloud/cloud.cfg.d/*.cfg.
