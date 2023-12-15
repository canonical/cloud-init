.. _stable_release_updates:

Stable Release Updates (SRU)
****************************

Once upstream cloud-init has released a new version, the Ubuntu Server team
backports cloud-init to previous releases via a special procedure called a
"Stable Release Update" (`SRU`_). This helps ensure that new versions of
cloud-init on existing releases of Ubuntu will not experience breaking
changes. Breaking changes are allowed when transitioning from one Ubuntu
series to the next (Focal -> Jammy).

SRU package version
===================

Ubuntu cloud-init packages follow the `SRU release version`_ format.

.. _sru_testing:

SRU testing for cloud-init
==========================

The cloud-init project has a specific process it follows when validating
a cloud-init SRU, which is documented in the `CloudinitUpdates`_ wiki page.

An SRU test of cloud-init performs the following:

    For each Ubuntu SRU, the Ubuntu Server team validates the new
    version of cloud-init on these platforms: **Amazon EC2, Azure, GCE,
    OpenStack, Oracle, Softlayer (IBM), LXD using the integration test
    suite.**

Test process:
-------------

The `integration test suite` used for validation follows these steps:

* :ref:`Install a pre-release version of cloud-init<ubuntu_test_pre_release>`
  from the **-proposed** APT pocket (e.g., **jammy-proposed**).
* Upgrade cloud-init and attempt a clean run of cloud-init to assert
  that the new version works properly on the specific platform and Ubuntu
  series.
* Check for tracebacks and errors in behaviour.

.. LINKS
.. include:: ../links.txt
.. _SRU: https://wiki.ubuntu.com/StableReleaseUpdates
.. _CloudinitUpdates: https://wiki.ubuntu.com/CloudinitUpdates
.. _new cloud-init bug: https://github.com/canonical/cloud-init/issues
.. _#cloud-init IRC channel: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _integration test suite: https://github.com/canonical/cloud-init/tree/main/tests/integration_tests
.. _SRU release version: https://github.com/canonical/ubuntu-maintainers-handbook/blob/main/VersionStrings.md#version-adding-a-change-in-ubuntu-as-a-stable-release-update
