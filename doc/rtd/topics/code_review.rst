*******************
Code Review Process
*******************

In order to manage incoming pull requests effectively, and provide
timely feedback and/or acceptance this document serves as a guideline
for the review process and outlines the expectations for those
submitting code to the project as well as those reviewing the code.
Code is reviewed for acceptance by at least one core team member (later
referred to as committers), but comments and suggestions from others
are encouraged and welcome.

The process is intended to provide timely and actionable feedback for
any submission.

Asking For Help
===============

cloud-init contributors, potential contributors, community members and
users are encouraged to ask for any help that they need.  If you have
questions about the code review process, or at any point during the
code review process, these are the available avenues:

* if you have an open Pull Request, comment on that pull request
* join the ``#cloud-init`` channel on the Freenode IRC network and ask
  away
* send an email to the cloud-init mailing list,
  cloud-init@lists.launchpad.net

These are listed in rough order of preference, but use whichever of
them you are most comfortable with.

Goals
=====

This process has the following goals:

* Ensure code reviews occur in a timely fashion and provide actionable
  feedback if changes are desired.
* Ensure the minimization of ancillary problems to increase the
  efficiency for those reviewing the submitted code

Role Definitions
================

Any code review process will have (at least) two involved parties.  For
our purposes, these parties are referred to as **Proposer** and
**Reviewer**.  (We also have the **Committer** role which is a special
case of the **Reviewer** role.)  The terms are defined here (and the
use of the singular form is not meant to imply that they refer to a
single person):

Proposer
   The person proposing a pull request (hereafter known as a PR).

Reviewer
   A person who is reviewing a PR.

Committer
   A cloud-init core developer (i.e. a person who has permission to
   merge PRs into master).

Prerequisites For Landing Pull Requests
=======================================

Before a PR can be landed into master, the following conditions *must*
be met:

* the CLA has been signed by the **Proposer** (or is covered by an
  entity-level CLA signature)
* all required status checks are passing
* at least one "Approve" review from a **Committer**
* no "Request changes" reviews from any **Committer**

The following conditions *should* be met:

* any Python functions/methods/classes have docstrings added/updated
* any changes to config module behaviour are captured in the
  documentation of the config module
* any Python code added has corresponding unit tests
* no "Request changes" reviews from any **Reviewer**

These conditions can be relaxed at the discretion of the
**Committers** on a case-by-case basis.  Generally, for accountability,
this should not be the decision of a single **Committer**, and the
decision should be documented in comments on the PR.

(To take a specific example, the ``cc_phone_home`` module had no tests
at the time `PR #237
<https://github.com/canonical/cloud-init/pull/237>`_ was submitted, so
the **Proposer** was not expected to write a full set of tests for
their minor modification, but they were expected to update the config
module docs.)

Non-Committer Reviews
=====================

Reviews from non-**Committers** are *always* welcome.  Please feel
empowered to review PRs and leave your thoughts and comments on any
submitted PRs, regardless of the **Proposer**.

Much of the below process is written in terms of the **Committers**.
This is not intended to reflect that reviews should only come from that
group, but acknowledges that we are ultimately responsible for
maintaining the standards of the codebase.  It would be entirely
reasonable (and very welcome) for a **Reviewer** to only examine part
of a PR, but it would not be appropriate for a **Committer** to merge a
PR without full scrutiny.

Opening Phase
=============

In this phase, the **Proposer** is responsible for opening a pull
request and meeting the prerequisites laid out above.

If they need help understanding the prerequisites, or help meeting the
prerequisites, then they can (and should!) ask for help.  See the
:ref:`Asking For Help` section above for the ways to do that.

These are the steps that comprise the opening phase:

1. The **Proposer** opens PR

2. CI runs automatically, and if

   CI fails
      The **Proposer** is expected to fix CI failures.  If the
      **Proposer** doesn't understand the nature of the failures they
      are seeing, they should comment in the PR to request assistance,
      or use another way of :ref:`Asking For Help`.

      (Note that if assistance is not requested, the **Committers**
      will assume that the **Proposer** is working on addressing the
      failures themselves.  If you require assistance, please do ask
      for help!)

   CI passes
      Move on to the :ref:`Review phase`.

Review Phase
============

In this phase, the **Proposer** and the **Reviewers** will iterate
together to, hopefully, get the PR merged into the cloud-init codebase.
There are three potential outcomes: merged, rejected permanently, and
temporarily closed.  (The first two are covered in this section; see
:ref:`Inactive Pull Requests` for details about temporary closure.)

(In the below, when the verbs "merge" or "squash merge" are used, they
should be understood to mean "squash merged using the GitHub UI", which
is the only way that changes can land in cloud-init's master branch.)

These are the steps that comprise the review phase:

1. **The Committers** assign a **Committer** to the PR

   This **Committer** is expected to shepherd the PR to completion (and
   merge it, if that is the outcome reached).  This means that they
   will perform an initial review, and monitor the PR to ensure that
   the **Proposer** is receiving any assistance that they require.  The
   **Committers** will perform this assignment on a daily basis.

   This assignment is intended to ensure that the **Proposer** has a
   clear point of contact with a cloud-init core developer, and that
   they get timely feedback after submitting a PR.  It *is not*
   intended to preclude reviews from any other **Reviewers**, nor to
   imply that the **Committer** has ownership over the review process.

   The assigned **Committer** may choose to delegate the code review of
   a PR to another **Reviewer** if they think that they would be better
   suited.

   (Note that, in GitHub terms, this is setting an Assignee, not
   requesting a review.)

2. That **Committer** performs an initial review of the PR, resulting
   in one of the following:

   Approve
     If the submitted PR meets all of the :ref:`Prerequisites for
     Landing Pull Requests` and passes code review, then the
     **Committer** will squash merge immediately.

     There may be circumstances where a PR should not be merged
     immediately.  The ``wip`` label will be applied to PRs for which
     this is true.  Only **Committers** are able to apply labels to
     PRs, so anyone who believes that this label should be applied to a
     PR should request its application in a comment on the PR.

     The review process is **DONE**.

   Approve (with nits)
     If the **Proposer** submits their PR with "Allow edits from
     maintainer" enabled, and the only changes the **Committer**
     requests are minor "nits", the **Committer** can push fixes for
     those nits and *immediately* squash merge.  If the **Committer**
     does not wish to fix these nits but believes they should block a
     straight-up Approve, then their review should be "Needs Changes"
     instead.

     A nit is understood to be something like a minor style issue or a
     spelling error, generally confined to a single line of code.

     If a **Committer** is unsure as to whether their requested change
     is a nit, they should not treat it as a nit.

     (If a **Proposer** wants to opt-out of this, then they should
     uncheck "Allow edits from maintainer" when submitting their PR.)

     The review process is **DONE**.

   Outright rejection
     The **Committer** will close the PR, with useful messaging for the
     **Proposer** as to why this has happened.

     This is reserved for cases where the proposed change is completely
     unfit for landing, and there is no reasonable path forward.  This
     should only be used sparingly, as there are very few cases where
     proposals are completely unfit.

     If a different approach to the same problem is planned, it should
     be submitted as a separate PR.  The **Committer** should include
     this information in their message when the PR is closed.

     The review process is **DONE**.

   Needs Changes
     The **Committer** will give the **Proposer** a clear idea of what
     is required for an Approve vote or, for more complex PRs, what the
     next steps towards an Approve vote are.

     The **Proposer** will ask questions if they don't understand, or
     disagree with, the **Committer**'s review comments.

     Once consensus has been reached, the **Proposer** will address the
     review comments.

     Once the review comments are addressed (as well as, potentially,
     in the interim), CI will run.  If CI fails, the **Proposer** is
     expected to fix CI failures.  If CI passes, the **Proposer**
     should indicate that the PR is ready for re-review (by @ing the
     assigned reviewer), effectively moving back to the start of this
     section.

Inactive Pull Requests
======================

PRs will be temporarily closed if they have been waiting on
**Proposer** action for a certain amount of time without activity.  A
PR will be marked as stale (with an explanatory comment) after 14 days
of inactivity.  It will be closed after a further 7 days of inactivity.

These closes are not considered permanent, and the closing message
should reflect this for the **Proposer**. However, if a PR is reopened,
it should effectively enter the :ref:`Opening phase` again, as it may
need some work done to get CI passing again.
