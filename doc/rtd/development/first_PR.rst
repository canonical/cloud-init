Contribution requirements
*************************

The following steps must be completed before a contribution can be accepted.

Understand contribution expectations
====================================

Read and agree to abide by our `Code of Conduct`_.

Make sure that you understand the
:ref:`code review process<code_review_process>`.

Sign the CLA
============

The Canonical `contributor license agreement <CLA_>`_ (CLA) must be signed
- for either an individual or on behalf of an organization. This is enforced
by CI.

Make a change
=============

Modify the source with your desired change.

Properly format the change
==========================

Auto-formatters can be used to make your changes satisfy the linters. ::

    tox -e do_format

Test the change
===============

Unit tests and linters can be executed with `tox`_. ::

    tox

Check out the :ref:`QEMU tutorial<tutorial_qemu>` to see how to run cloud-init
in a virtual machine. This can often be used to verify a change.

Contribute the change
=====================

Submit a PR against the ``main`` branch of the canonical/cloud-init repository.

A Github Issue must be filed which describes the issue / feature that is
resolved by your PR. This issue must be linked to from the PR.

Take special care to follow the template format and describe why the change is
required.

Follow up
=========

All CI jobs must pass. If a job failes that seems unrelated to your change, it
may be a temporary issue with Github. Pushing an empty commit will force CI to
re-run.

Your PR may not be reviewed immediately, but maintainers regularly monitor the
queue. Changes may be requested by maintainers which must be addressed before
the PR will be merged. PRs will be closed after they go stale. If a PR goes
stale without response, feel free to ping a maintainer for feedback. 

Questions
=========

For help with the process, email
`Chad Smith <mailto:chad.smith@canonical.com>`_ with the subject:
"Cloud-init CLA".

.. include:: ../links.txt
