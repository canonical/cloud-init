Contribution requirements
*************************

The following steps must be completed before a contribution can be accepted.

Understand the process
======================

Make sure that you understand the
:ref:`code review process<code_review_process>`.

Sign the CLA
============

The Canonical `contributor license agreement <CLA_>`_ (CLA) must be signed
- for either an individual or on behalf of an organization.

Make a change
=============

Modify the source with your desired change.

Properly format the change
==========================

Auto-formatters can be used to make your changes satisfy linters. ::

    tox -e do_format

Verify that tests pass
======================

Unit tests and linters can be executed with `tox`_. ::

    tox

Open a PR on Github
===================

A Github Issue must be filed which describes the issue / feature that your PR
resolves. This issue must be linked to from the PR. This is not required for
simple PRs.

Take special care to follow the template format and describe why the change is
required. Simply describing the modifications is not sufficient except in simple
PRs (ex: spelling / grammar changes).

Follow up
=========

Your PR may not be reviewed immediately, but maintainers regularly
monitor the queue. Changes may be requested which must be addressed before the
PR can be merged. PRs will be closed after they go stale. If a PR goes stale
without response, feel free to ping a maintainer for feedback. 


Questions
=========

For help with the process, email
`Chad Smith <mailto:chad.smith@canonical.com>`_ with the subject:
"Cloud-init CLA".
