.. _development:

Development requirements
************************

The following steps must be completed to develop cloud-init. A pull request
that fails to meet the contribution requirements is unlikely to merge.

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

Clone the repository
====================

One must understand `how to use Git and GitHub`_. Create a local clone of the
repository: ::

    git clone git@github.com:canonical/cloud-init.git

Make a change
=============

Modify the source: fix a bug or add a feature. Make sure to update comments
and docs, avoid unnecessary code changes, and remove any code which is no
longer used. Functions, methods, and classes should include docstrings and type
annotations.

Format the change
=================

Changes that are inconsistent with the style and conventions of the existing
code are undesireable. CI jobs run linters to enforce certain rules.
Auto-formatting the code prevents most linter failures: ::

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
Unit tests can be executed with `tox`_: ::

    tox -e py3

Proposed changes should not reduce test coverage. Existing tests in ``tests/``
may serve as a source of inspiration for new tests. Read more
:ref:`here<testing>`.

Integration tests
-----------------

Integration tests may also be required, depending on the scope of the change.

Linters
-------

If a linter is silenced, a code comment must document the justification for
this decision.

Run linters with: ::

    tox -e check_format

Document the change
===================

Changes that modify behavior of cloud-init must be documented. Documentation
can be built locally with: ::

    tox -e doc

Read more about contributing to documentation :ref:`here<docs>`.

Propose the change
==================

Submit a PR against the ``main`` branch of the `canonical/cloud-init`_
repository. Take special care when filling in the PR description template to
include all requested information. Make sure to reference the issue in the PR
description using the ``#<PR num>`` syntax and also include the PR number in
the proposed commit message using ``Fixes GH-<PR num>`` at the end of the
commit message.

All CI jobs must pass. If a job fails that seems unrelated to your change, it
may be a temporary issue with Github. Push an empty commit if you need to
re-run CI.

Respond to feedback
===================

A PR may not be reviewed immediately, but the queue is actively monitored.
Changes requested by core developers must be resolved before the PR can merge.

A **stale** tag is added to the PR after 14 days of inactivity and it is
automatically closed after 7 more.

Any PR that does not meet the requirements might be assumed to be under
development. If a PR has gone stale and you are certain that it meets the
documented requirements, then you may ping a core developer.

.. toctree::
   :maxdepth: 1
   :hidden:

   Develop code <contribute_code.rst>
   Develop docs <contribute_docs.rst>
   Read dev docs <dev_docs.rst>

.. _how to use Git and GitHub: https://docs.github.com/en/get-started/start-your-journey
.. _canonical/cloud-init: https://github.com/canonical/cloud-init
.. include:: ../links.txt
