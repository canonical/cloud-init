*******************
Code Review Process
*******************

In order to manage incoming pull requests effectively, and to ensure
that community members (like you!) submitting them understand what to
expect, cloud-init has a documented code review process.

The language used is intentionally formal, in a bid to avoid ambiguity,
but the *experience* of working through the code review process should
not be, so please don't be put off!  If you have any questions about
this process, please do ask them in ``#cloud-init`` on the Freenode IRC
network.

Goals
=====

This process has the following goals:

* Ensure that cloud-init community members are receiving code reviews
  in a timely fashion
* Minimize the time the cloud-init core developers have to spend on the
  parts of the code review process which aren't actual code review

Roles
=====

For ease of understanding, we will refer to two different roles
throughout the process:

Proposer
   The developer proposing a pull request (hereafter known as a PR).
   This could be a core developer or community member.  (This is likely
   the role you will be taking in this process.)

the Committers
   The group of cloud-init core developers.

   In this process doc, cloud-init core developers are treated as a
   bloc of interchangeable people.  This is a simplification, as in
   reality we will need to manage transfer of reviews, dismissal of
   stale reviews, parallel reviews from multiple committers, etc.  If
   we find that handling these on an ad-hoc basis is causing problems,
   then we should revisit and expand this process to include them.

   (If the **Proposer** is a core developer, then they are not
   considered part of this group for the purposes of this process.)

Opening Phase
=============

In this phase, the **Proposer** is responsible for all actions. They
should get a PR into good enough shape that it is worth **the
Committers** spending time reviewing it.  Specifically, they are
responsible for getting to a point where the continuous integration
(CI) testing in Travis is passing.  Once a PR is passing CI, it moves
into the :ref:`Review phase`.

These are the steps that comprise the opening phase:

1. The **Proposer** opens PR

2. An automated comment will be added to the PR, outlining the steps
   expected of the **Proposer** before a **Committer** will review
   their PR.  (N.B. This automation is not yet implemented!)

3. CI runs automatically, and if

   CI fails
      The **Proposer** is expected to fix CI failures.  If the
      **Proposer** doesn't understand the nature of the failures they
      are seeing, they should comment in the pull request to request
      assistance.  Alternatively, for more immediate assistance, they
      can ask in ``#cloud-init`` on the Freenode IRC network.

   CI passes
      Move on to the :ref:`Review phase`.

Review Phase
============

In this phase, the **Proposer** and the **Committers** will iterate
together to, hopefully, get the PR merged into the cloud-init codebase.
There are three potential outcomes: merged, rejected permanently, and
temporarily closed.

These are the steps that comprise the review phase:

1. **The Committers** assign a **Committer** to the PR

   The cloud-init core developers will work amongst themselves to
   ensure that this happens in a timely fashion.  (Generally,
   assignment will happen at the team's daily internal meeting.)  Note
   that, in GitHub terms, this is setting an Assignee, not requesting a
   review.

2. That **Committer** reviews the PR, resulting in one of the
   following:

   Approve
     The **Committer** will squash merge immediately.

     There may be circumstances where a PR should not be merged
     immediately; these will be handled case-by-case, and the
     **Proposer** should make this requirement very clear in their pull
     request description.

     The review process is **DONE**.

   Approve (with nits)
     If the **Proposer** submits their PR with "Allow edits from
     maintainer" enabled, and the only changes the **Committer**
     requests are minor "nits", the **Committer** can push fixes for
     those nits and squash merge.  (If a **Proposer** wants to opt-out
     of this, then they should uncheck "Allow edits from maintainer"
     when submitting their PR.)

     A nit is understood to be something like a minor style issue or a
     spelling error, generally confined to a single line of code.

     If a **Committer** is unsure as to whether their requested change
     is a nit, they should not treat it as a nit.

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

PRs may be closed if they have been waiting on **Proposer** action for
a certain amount of time without activity.  A PR will be marked as
stale (with an explanatory comment) after 14 days of inactivity.  It
will be closed after a further 7 days of inactivity.

These closes are not considered permanent, and the closing message
should reflect this for the **Proposer**. However, if a PR is reopened,
it should effectively enter the :ref:`Opening phase` again, as it may need
some work done to get CI passing again.
