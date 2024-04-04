.. _breaking_changes:

Breaking Changes
****************

This section provides reference and guidance on specific breaking changes to 
cloud-init releases. 

24.1 - removed Ubuntu's ordering dependency on snapd.seeded
===========================================================

In Ubuntu releases, cloud-init will no longer wait on snapd preseeding to run.
If a user-provided script relies on a snap, it must now be prefixed with
`snap wait system seed.loaded` to ensure the snaps are ready for use.  For
example, a cloud config that previously included:

.. code-block:: yaml

runcmd:
    - [ snap, install, mc-installer ]


Will now need to be:

.. code-block:: yaml

runcmd:
    - [ snap, wait, system, seed.loaded ]
    - [ snap, install, mc-installer ]


23.4 - status codes
===================

something something if you have a script that relies on cloud-init status
return values make sure to update it?
