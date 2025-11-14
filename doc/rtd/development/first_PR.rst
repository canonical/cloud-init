.. _first-PR:

Contribution requirements
*************************

The following steps must be completed to contribute to cloud-init. A PR that
fails to meet the contribution requirements is unlikely to be successful.

Understand contribution expectations
====================================

Read and agree to abide by the `Code of Conduct`_.

Sign the CLA
============

The Canonical `contributor license agreement <CLA_>`_ (CLA) must be signed
- as either an individual or on behalf of an organization. This is enforced
by CI. For help with the CLA, email
`Chad Smith <mailto:chad.smith@canonical.com>`_ with the subject:
"Cloud-init CLA".

Make a change
=============

Modify the source: fix a bug or add a feature. Make sure to update comments
and docs, limit unnecessary code changes, and remove any code that is no longer
used. Functions, methods, and classes should include docstrings and type
annotations.

Format the change
=================

Changes that are inconsistent with the style and conventions of the existing
code are undesireable. CI jobs run linters to enforce certain rules.
Auto-formatting the code catches most issues: ::

    tox -e do_format

Test the change
===============

Manual tests
------------

Before submitting a PR, one should verify that the change produces the desired
result. While verifying the change, make sure to capture evidence of manual
testing (CLI output or logs) to include in the PR description for reviewers.
See the :ref:`QEMU tutorial<tutorial_qemu>` for instructions to run cloud-init
in a virtual machine - this is often sufficient to manually test changes.

Unit tests
----------

Unit tests should be added to verify discrete chunks of code.
Unit tests and linters can be executed with `tox`_: ::

    tox

Proposed changes should not reduce test coverage. Existing tests in ``tests/``
may serve as a source of inspiration for new tests.

Integration tests
-----------------

Integration tests may also be required, depending on the scope of the change.

Linters
-------

If a linter is silenced, a code comment should document the justification for
this decision.

Run linters with: ::

    tox -e check_format

Document the change
===================

Changes that modify behavior of cloud-init must be documented. The docs can be
build locally with: ::

    tox -e doc

Contribute the change
=====================

Submit a PR against the ``main`` branch of the `canonical/cloud-init`_
repository. Take special care when filling in the PR description template to
include all requested information. A Github Issue must be linked to the PR that
describes the issue or feature.

All CI jobs must pass. If a job failes that seems unrelated to your change, it
may be a temporary issue with Github. Push an empty commit if you need to
re-run CI.

PR lifecycle
============

A PR may not be reviewed immediately, but the queue is actively monitored.
Changes requested by core developers must be resolved before the PR can be
merged.

A **stale** tag is added to the PR after 14 days of inactivity and it is
automatically closed after 7 more.

Any PR that does not meet the requirements might be assumed by core developers
to be under development. If a PR has gone stale and you are certain that it
meets the documented requirements, then you may ping a core developer.

.. _canonical/cloud-init: https://github.com/canonical/cloud-init
.. include:: ../links.txt
