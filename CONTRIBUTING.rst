.. _contributing:

Contributing to ``cloud-init``
******************************

This document describes how to contribute changes to ``cloud-init``.
It assumes you have a `GitHub`_ account, and refers to your GitHub user
as ``GH_USER`` throughout.

Submitting your first pull request
==================================

Summary
-------

Before any pull request can be accepted, you must do the following:

* Sign the Canonical `contributor license agreement`_.
* Add your GitHub username (alphabetically) to the in-repository list that we
  use to track CLA signatures: `tools/.github-cla-signers`_.
* Add or update any :ref:`unit tests<testing>` accordingly.
* Add or update any :ref:`integration_tests` (if applicable).
* Format code (using ``black`` and ``isort``) with `tox -e do_format`.
* Ensure unit tests and linting pass using `tox`_.
* Submit a PR against the ``main`` branch of the ``cloud-init`` repository.

The detailed instructions
-------------------------

Follow these steps to submit your first pull request to ``cloud-init``:

* To contribute to ``cloud-init``, you must sign the Canonical
  `contributor license agreement`_.

  * If you have already signed it as an individual, your Launchpad user
    will be listed in the `contributor-agreement-canonical`_ group.
    Unfortunately there is no easy way to check if an organization or
    company you are doing work for has signed.

  * When signing it:

    * ensure that you fill in the GitHub username field,
    * when prompted for 'Project contact' or 'Canonical Project
      Manager', enter 'James Falcon'.

  * If your company has signed the CLA for you, please contact us to
    help in verifying which Launchpad/GitHub accounts are associated
    with the company.

  * For any questions or help with the process, please email `James
    Falcon <mailto:james.falcon@canonical.com>`_ with the subject,
    "Cloud-init CLA".

  * You also may contact user ``falcojr`` in the ``#cloud-init``
    channel on the `Libera IRC network`_.

* Configure ``git`` with your email and name for commit messages.

  Your name will appear in commit messages and will also be used in
  changelogs or release notes. Give yourself credit! ::

    git config user.name "Your Name"
    git config user.email "Your Email"

* Sign in to your `GitHub`_ account.

* Fork the upstream `repository`_ on GitHub and click on the ``Fork`` button

* Create a new remote pointing to your personal GitHub repository.

.. code-block:: sh

    git clone git@github.com:GH_USER/cloud-init.git
    cd cloud-init
    git remote add upstream git@github.com:canonical/cloud-init.git
    git push origin main

* Read through the ``cloud-init``
  :ref:`Code Review Process<code_review_process>`, so you understand
  how your changes will end up in ``cloud-init``'s codebase.

* Submit your first ``cloud-init`` pull request, adding your GitHub username
  to the in-repository list that we use to track CLA signatures:
  `tools/.github-cla-signers`_

  * See `PR #344`_ and `PR #345`_ for examples of what this pull
    request should look like.

  * Note that ``.github-cla-signers`` is sorted alphabetically.

  * If you already have a change that you want to submit, you can
    also include the change to ``tools/.github-cla-signers`` in that
    pull request, there is no need for two separate PRs.

Transferring CLA Signatures from Launchpad to GitHub
----------------------------------------------------

For existing contributors who signed the agreement in Launchpad before the
GitHub username field was included, we need to verify the link between your
`Launchpad`_ account and your `GitHub`_ account. To enable us to do this, we
ask that you create a branch with both your Launchpad and GitHub usernames
against both the Launchpad and GitHub ``cloud-init`` repositories. We've added
a tool (``tools/migrate-lp-user-to-github``) to the ``cloud-init`` repository
to handle this migration as automatically as possible.

The ``cloud-init`` team will review the two merge proposals, verify that the
CLA has been signed for the Launchpad user, and record the associated GitHub
account.

.. note::
   If you are a first time contributor, you will not need to touch
   Launchpad to contribute to ``cloud-init``. All new CLA signatures are
   handled as part of the GitHub pull request process described above.

Do these things for each feature or bug
=======================================

* Create a new topic branch for your work: ::

    git checkout -b my-topic-branch

* Make and commit your changes (note, you can make multiple commits,
  fixes, and add more commits.): ::

    git commit

* Apply ``black`` and ``isort`` formatting rules with `tox`_: ::

    tox -e do_format

* Run unit tests and lint/formatting checks with `tox`_: ::

    tox

* Push your changes to your personal GitHub repository: ::

    git push -u origin my-topic-branch

* Use your browser to create a pull request:

  - Open the branch on GitHub

    - You can see a web view of your repository and navigate to the branch at:
      ::

         https://github.com/GH_USER/cloud-init/tree/my-topic-branch

  - Click :guilabel:`Pull Request`.
  - Fill out the pull request title, summarizing the change and a longer
    message indicating important details about the changes included, like: ::

      Activate the frobnicator.

      The frobnicator was previously inactive and now runs by default.
      This may save the world some day. Then, list the bugs you fixed
      as footers with syntax as shown here.

      The commit message should be one summary line of less than
      70 characters followed by a blank line, and then one or more
      paragraphs wrapped at 72 characters describing the change and why
      it was needed.

      This is the message that will be used on the commit when it
      is sqaushed and merged into main. If there is a related launchpad
      bug, specify it at the bottom of the commit message.

      LP: #NNNNNNN (replace with the appropriate bug reference or remove
      this line entirely if there is no associated bug)

    Note that the project continues to use LP: #NNNNN format for closing
    launchpad bugs rather than GitHub Issues.

  - Click :guilabel:`Create Pull Request`

Then, a ``cloud-init`` committer will review your changes and
follow up in the pull request. Look at the :ref:`Code Review Process<code_review_process>` doc to understand the following steps.

Feel free to ping and/or join ``#cloud-init`` on Libera IRC if you
have any questions.

Design
======

This section captures design decisions that are helpful to know when
hacking on ``cloud-init``.

Python support
--------------

``Cloud-init`` upstream currently supports Python 3.6 and above.

``Cloud-init`` upstream will stay compatible with a particular Python version
for 6 years after release. After 6 years, we will stop testing upstream
changes against the unsupported version of Python and may introduce
breaking changes. This policy may change as needed.

The following table lists the ``cloud-init`` versions in which the
minimum Python version changed:

================== ==================
Cloud-init version Python version
================== ==================
22.1               3.6+
20.3               3.5+
19.4               2.7+
================== ==================

Cloud Config Modules
--------------------

* Any new modules should use underscores in any new config options and not
  hyphens (e.g. `new_option` and *not* `new-option`).

Tests
-----

Submissions to ``cloud-init`` must include testing. See :ref:`testing` for
details on these requirements.

Type annotations
----------------

The ``cloud-init`` codebase uses Python's annotation support for storing
``type`` annotations in the style specified by `PEP-484`_ and `PEP-526`_.
Their use in the codebase is encouraged.

Feature Flags
-------------

.. automodule:: cloudinit.features
   :members:

.. LINKS:
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _Libera IRC network: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _GitHub: https://github.com
.. _Launchpad: https://launchpad.net
.. _repository: https://github.com/canonical/cloud-init
.. _contributor license agreement: https://ubuntu.com/legal/contributors
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
.. _tox: https://tox.readthedocs.io/en/latest/
.. _PEP-484: https://www.python.org/dev/peps/pep-0484/
.. _PEP-526: https://www.python.org/dev/peps/pep-0526/
