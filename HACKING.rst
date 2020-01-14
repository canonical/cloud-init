*********************
Hacking on cloud-init
*********************

This document describes how to contribute changes to cloud-init.
It assumes you have a `GitHub`_ account, and refers to your GitHub user
as ``GH_USER`` throughout.

Do these things once
====================

* To contribute, you must sign the Canonical `contributor license agreement`_

  If you have already signed it as an individual, your Launchpad user will be
  listed in the `contributor-agreement-canonical`_ group.  Unfortunately there
  is no easy way to check if an organization or company you are doing work for
  has signed.  When signing the CLA and prompted for 'Project contact' or
  'Canonical Project Manager' enter 'Josh Powers'.

  For first-time signers, or for existing contributors who have already signed
  the agreement in Launchpad, we need to verify the link between your
  `Launchpad`_ account and your `GitHub`_ account.  To enable us to do this, we
  ask that you create a branch with both your Launchpad and GitHub usernames
  against both the Launchpad and GitHub cloud-init repositories.  We've added a
  tool (``tools/migrate-lp-user-to-github``) to the cloud-init repository to
  handle this migration as automatically as possible.

  The cloud-init team will review the two merge proposals and verify
  that the CLA has been signed for the Launchpad user and record the
  associated GitHub account.  We will reply to the email address
  associated with your Launchpad account that you've been clear to
  contribute to cloud-init on GitHub.

  If your company has signed the CLA for you, please contact us to help
  in verifying which launchad/GitHub accounts are associated with the
  company.  For any questions or help with the process, please email:

  `Josh Powers <mailto:josh.powers@canonical.com>`_ with the subject: Cloud-Init CLA

   You also may contanct user ``powersj`` in ``#cloud-init`` channel via IRC freenode.

* Configure git with your email and name for commit messages.

  Your name will appear in commit messages and will also be used in
  changelogs or release notes.  Give yourself credit!::

    git config user.name "Your Name"
    git config user.email "Your Email"

* Sign into your `GitHub`_ account

* Fork the upstream `repository`_ on Github and clicking on the ``Fork`` button

* Create a new remote pointing to your personal GitHub repository.

  .. code:: sh

    git clone git://github.com/canonical/cloud-init
    cd cloud-init
    git remote add GH_USER git@github.com:GH_USER/cloud-init.git
    git push GH_USER master

.. _GitHub: https://github.com
.. _Launchpad: https://launchpad.net
.. _repository: https://github.com/canonical/cloud-init
.. _contributor license agreement: http://www.canonical.com/contributors
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members

Do these things for each feature or bug
=======================================

* Create a new topic branch for your work::

    git checkout -b my-topic-branch

* Make and commit your changes (note, you can make multiple commits,
  fixes, more commits.)::

    git commit

* Run unit tests and lint/formatting checks with `tox`_::

    tox

* Push your changes to your personal GitHub repository::

    git push -u GH_USER my-topic-branch

* Use your browser to create a merge request:

  - Open the branch on GitHub

    - You can see a web view of your repository and navigate to the branch at:

      ``https://github.com/GH_USER/cloud-init/tree/my-topic-branch``

  - Click 'Pull Request`
  - Fill out the pull request title, summarizing the change and a longer
    message indicating important details about the changes included, like ::

      Activate the frobnicator.

      The frobnicator was previously inactive and now runs by default.
      This may save the world some day.  Then, list the bugs you fixed
      as footers with syntax as shown here.

      The commit message should be one summary line of less than
      74 characters followed by a blank line, and then one or more
      paragraphs describing the change and why it was needed.

      This is the message that will be used on the commit when it
      is sqaushed and merged into trunk.

      LP: #1

    Note that the project continues to use LP: #NNNNN format for closing
    launchpad bugs rather than GitHub Issues.

  - Click 'Create Pull Request`

Then, someone in the `Ubuntu Server`_ team will review your changes and
follow up in the pull request.

Feel free to ping and/or join ``#cloud-init`` on freenode irc if you
have any questions.

.. _tox: https://tox.readthedocs.io/en/latest/
.. _Ubuntu Server: https://github.com/orgs/canonical/teams/ubuntu-server

Design
======

This section captures design decisions that are helpful to know when
hacking on cloud-init.

Cloud Config Modules
--------------------

* Any new modules should use underscores in any new config options and not
  hyphens (e.g. `new_option` and *not* `new-option`).
