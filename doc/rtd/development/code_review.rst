.. _code_review_process:

Code review process
*******************

Code is reviewed for acceptance by at least one core team member (later
referred to as committers), but comments and suggestions from others
are encouraged and welcome.

Goals
=====

This process aims to:

* provide timely and actionable feedback on every submission,
* make sure incoming PRs are handled efficiently, and
* get PRs accepted within a reasonable time frame.

.. _asking-for-help:

Asking for help
===============

Cloud-init contributors, community members and users are encouraged to ask for
help if they need it. If you have questions about the code review process, or
need advice on an open PR, these are the available avenues:

* Open a PR, add "WIP:" to the title, and leave a comment on that PR
* join the ``#cloud-init`` `channel on the Libera IRC <IRC_>`_ network
* post on the ``#cloud-init`` `Discourse topic <Discourse_>`_
* send an email to the cloud-init mailing list: ::

    cloud-init@lists.launchpad.net

These are listed in order of our preference, but please use whichever of them
you are most comfortable with.

Role definitions
================

There are three roles involved in code reviews:

* **Proposer**

  The person(s) submitting the PR

* **Reviewer**

  A person who is reviewing the PR

* **Committer**

  A cloud-init core developer (i.e., someone with permission to merge PRs
  into ``main``)

.. _PR-acceptance:

PR acceptance conditions
========================

Before a PR can be accepted and merged into ``main`` ("landed"), the following
conditions **must** be met:

* The `CLA`_ must be signed **by the proposer** (unless the proposer is
  covered by an entity-level CLA signature),
* All required status checks must be passing,
* At least one "Approve" review must be given **by a committer**, and
* No "Request changes" reviews from a committer can be outstanding.

The following conditions **should** be met:

* Any Python functions/methods/classes have docstrings added/updated,
* Any changes to config module behaviour are captured in that module's
  documentation,
* Any Python code added has corresponding :ref:`unit tests<testing>`, and
* No "Request changes" reviews from any **reviewer** are outstanding.

These conditions can be relaxed at the discretion of the committers on a
case-by-case basis. For accountability, this should not be the decision of a
single committer, and the decision should be documented in comments on the
PR.

To take a specific example, the ``cc_phone_home`` module had no tests
at the time `PR #237`_ was submitted, so the **proposer** was not expected to
write a full set of tests for their minor modification, but they *were*
expected to update the config module docs.

Non-committer reviews
=====================

Reviews from non-committer reviewers are *always* welcome. Please feel
empowered to review PRs and leave your thoughts and comments on any submitted
PR, regardless of the proposer.

Much of the below process is written in terms of the **committers**. This does
not mean that reviews should only come from that group, but rather acknowledges
that we are ultimately responsible for maintaining the standards of the
codebase. It is reasonable (and very welcome) for a reviewer to only examine
part of a PR, but a committer must not merge a PR without full scrutiny.

Opening phase
=============

Proposer opens a PR
-------------------

In this phase, the proposer opens a pull request and needs to ensure they meet
the criteria laid out above. If they need help understanding or meeting these
criteria, then they can (and should!) ask for help.

CI runs automatically
---------------------

* If CI fails:

  The **proposer** is expected to fix CI failures. If they don't understand the
  failures, they should comment on the PR to ask for help (or use another way
  of :ref:`asking-for-help`). If they don't ask for help, the
  committers will assume the proposer is working on addressing the failures.

* If CI passes:

  Move on to the **review phase**.

Review phase
============

In this phase, the **proposer** and the **reviewers** will work iteratively
together to get the PR merged into the cloud-init codebase.

There are three potential outcomes: **merged**, **rejected permanently**, and
**temporarily closed**. The first two are covered in this section; see
the :ref:`inactive pull requests<inactive-PRs>` section for details about
temporary closure.

A committer is assigned
-----------------------

The committers assign a committer to the PR. This committer is
expected to shepherd the PR to completion (and to merge it, if that is the
outcome reached).

They perform an initial review, and monitor the PR to ensure the proposer is
receiving help if they need it. The committers perform this assignment on a
regular basis for any new PRs submitted.

Committer's initial review
--------------------------

The assigned committer performs an initial review of the PR, resulting in one
of the following.

Approve
~~~~~~~

If the submitted PR meets all of the
:ref:`PR acceptance conditions<PR-acceptance>` and passes code review, then the
committer will squash merge immediately.

Sometimes, a PR should not be merged immediately. The :guilabel:`wip` label
will be applied to PRs for which this is true. Only committers are able to
apply labels to PRs, so anyone who thinks this label should be applied to a
PR should request it in a comment on the PR.

- The review process is **DONE**.

Approve (with nits)
~~~~~~~~~~~~~~~~~~~

A "nit" is understood to be something like a minor style issue or a spelling
error, generally confined to a single line of code.

If the proposer submits their PR with :guilabel:`"Allow edits from maintainer"`
enabled, and the only changes the committer requests are minor nits, the
committer can push fixes for those nits and immediately squash merge.

If the committer does not wish to fix these nits but believes they should
block a straightforward `Approve`, then their review should be
`Needs Changes` instead.

If a committer is unsure whether their requested change is a nit, they should
not treat it as a nit.

If a proposer wants to opt-out of this, they should uncheck
:guilabel:`"Allow edits from maintainer"` when submitting their PR.

- The review process is **DONE**.

Outright rejection
~~~~~~~~~~~~~~~~~~

The committer will close the PR with a message for the proposer to explain why.

This is reserved for cases where the proposed change is unfit for landing and
there is no reasonable path forward. This should only be used sparingly, as
there are very few cases where proposals are *completely* unfit.

If a different approach to the same problem is planned, it should be
submitted as a separate PR. The committer should include this information in
their message when the PR is closed.

- The review process is **DONE**.

Needs Changes
~~~~~~~~~~~~~

The committer will give the proposer clear feedback on what is needed for an
`Approve` vote or, for more complex PRs, what the next steps towards an
`Approve` vote are.

The proposer can ask questions if they don't understand, or disagree with, the
committer's review comments.

Once agreement has been reached, the proposer will address the review comments.

Once the review comments are addressed, CI will run. If CI fails, the proposer
is expected to fix any CI failures. If CI passes, the proposer should indicate
that the PR is ready for re-review (by `@` mentioning the assigned reviewer),
effectively moving back to the start of the `Review phase`.

.. _inactive-PRs:

Inactive pull requests
======================

PRs will be temporarily closed if they have been waiting on proposer action for
a certain amount of time without activity. A PR will be marked as **stale**
(with an explanatory comment) after 14 days of inactivity.

It will be closed after a further 7 days of inactivity.

These closes are not considered permanent, and the closing message should
reflect this for the proposer. However, if a PR is re-opened, it should
effectively re-enter the `Opening phase`, as it may need some work done
to get CI passing again.

.. LINKS:
.. include:: ../links.txt
.. _PR #237: https://github.com/canonical/cloud-init/pull/237
