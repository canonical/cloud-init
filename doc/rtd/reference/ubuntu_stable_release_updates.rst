.. _stable_release_updates:

Stable Release Updates (SRU)
****************************

For each upstream cloud-init release, a backport is preformed to
previous Ubuntu releases via a "Stable Release Update" (`SRU`_).
Each SRU ensures that new versions of cloud-init on existing releases
of Ubuntu will not experience breaking changes. Breaking changes are allowed
when transitioning from one Ubuntu series to the next (Focal -> Jammy).

.. _sru_supported_releases:

SRU supported releases
======================

Cloud-init will provide SRU support for the current active interim releases
and the most recent 2 long-term support (LTS) releases as documented in the
`Ubuntu Release Cycle`_

Security Updates
================
The `Ubuntu CVE policy`_ governs how Ubuntu mitigates CVEs in upstream and
the standard support Ubuntu releases and releases covered by
`Expanded Security Maintenance`_.

SRU package version
===================

Ubuntu cloud-init packages follow the `SRU release version`_ format.

.. _sru_testing:

SRU testing for cloud-init
==========================

The cloud-init project has a specific process it follows when validating
a cloud-init SRU, which is documented in the `CloudinitUpdates`_ documentation.

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
* Check for tracebacks and errors in behavior.

.. LINKS
.. include:: ../links.txt
.. _Ubuntu Release Cycle: https://ubuntu.com/about/release-cycle
.. _Ubuntu CVE policy: https://ubuntu.com/security/cves/about
.. _Expanded Security Maintenance: https://ubuntu.com/security/esm
.. _SRU: https://ubuntu.com/project/docs/SRU/stable-release-updates/
.. _CloudinitUpdates: https://ubuntu.com/project/docs/SRU/reference/exception-Cloudinit-Updates/
.. _integration test suite: https://github.com/canonical/cloud-init/tree/main/tests/integration_tests
.. _SRU release version: https://github.com/canonical/ubuntu-maintainers-handbook/blob/main/VersionStrings.md#version-adding-a-change-in-ubuntu-as-a-stable-release-update
