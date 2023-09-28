Submit your first pull request
******************************

Follow these steps to submit your first pull request to cloud-init:

Sign the CLA
============

To contribute to cloud-init, you must first sign the Canonical
`contributor license agreement <CLA_>`_ (CLA).

If you have already signed it as an individual, your Launchpad username will be
listed in the `contributor-agreement-canonical`_ group. Unfortunately there is
no easy way to check if the organisation or company you are working for has
signed it.

When you sign:

* ensure that you fill in the GitHub username field,
* when prompted for a 'Project contact' or 'Canonical Project Manager', enter
  'James Falcon'.

If your company has signed the CLA for you, please contact us to help in
verifying which Launchpad/GitHub accounts are associated with the company.

For any questions or help with the process, email
`James Falcon <mailto:james.falcon@canonical.com>`_ with the subject:
"Cloud-init CLA". You can also contact user ``falcojr`` in the #cloud-init
channel on the `Libera IRC network <IRC_>`_.

Configure git
=============

Next, configure ``git`` with your email and name for commit messages.

Your name will appear in commit messages and will also be used in changelogs or
release notes. Give yourself credit! ::

  git config user.name "Your Name"
  git config user.email "Your Email"

Clone the repository
====================

* Sign in to your `GitHub`_ account.

* From the cloud-init `upstream repository <GH repo_>`_ on GitHub, click on the
  :guilabel:`Fork` button.

* Create a new remote pointing to your personal GitHub repository.

  .. code-block:: sh

      git clone git@github.com:GH_USER/cloud-init.git
      cd cloud-init
      git remote add upstream git@github.com:canonical/cloud-init.git
      git push origin main

  Remember to change ``GH_USER`` to your GitHub username.

Work on your feature or bug
===========================

Create a new topic branch for your work: ::

    git checkout -b my-topic-branch

Create a virtual environment
----------------------------

It is very often helpful to create a safe and sandboxed environment to test
your changes in while you work. If you are not sure how to do this, check out
:ref:`our QEMU tutorial<tutorial_qemu>`, which walks through this process
step-by-step.

Make your commits
-----------------

Make and commit your changes (note, you can make multiple commits, fixes, and
add more commits): ::

    git commit

Add your name to the CLA signers list
-------------------------------------

As part of your first PR to cloud-init, you should also add your GitHub
username (alphabetically) to the in-repository list that we use to track CLA
signatures: `tools/.github-cla-signers`_.

`PR #344`_ and `PR #345`_ are good examples of what this should look like in
your pull request.

Format the code
---------------

Apply the ``black`` and ``isort`` formatting rules with `tox`_: ::

    tox -e do_format

Run unit tests
--------------

Run unit tests and lint/formatting checks with `tox`_: ::

    tox

Push your changes
-----------------

Push your changes to your personal GitHub repository: ::

    git push -u origin my-topic-branch

Create a pull request
=====================

Use your browser to create a pull request:

- Open the branch on GitHub

- You can see a web view of your repository and navigate to the branch at: ::

      https://github.com/GH_USER/cloud-init/tree/my-topic-branch

- Click :guilabel:`Pull Request`.

- Fill out the pull request title, summarizing the change and a longer message
  indicating important details about the changes included, like:

  .. code-block:: text

     Activate the frobnicator.

     The frobnicator was previously inactive and now runs by default.
     This may save the world some day. Then, list the bugs you fixed
     as footers with syntax as shown here.

     The commit message should be one summary line of less than
     70 characters followed by a blank line, and then one or more
     paragraphs wrapped at 72 characters describing the change and why
     it was needed.

     This is the message that will be used on the commit when it
     is squashed and merged into main. If there is a related launchpad
     bug, specify it at the bottom of the commit message.

     LP: #NNNNNNN (replace with the appropriate bug reference or remove this line entirely if there is no associated Launchpad bug)
     Fixes GH-00000 (replace with the appropriate GitHub issue number or remove this line if there's no associated GitHub issue)

  Note that the project continues to use LP: #NNNNN format for closing
  Launchpad bugs rather than GitHub Issues.

- Click :guilabel:`Create Pull Request`

Read our code review process
============================

Once you have submitted your PR (if not earlier!) you will want to read the
cloud-init :ref:`Code Review Process<code_review_process>`, so you can
understand how your changes will end up in cloud-init's codebase.

.. include:: ../links.txt
.. _quickstart documentation: https://docs.github.com/en/get-started/quickstart
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _repository: https://github.com/canonical/cloud-init
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
.. _PEP-484: https://www.python.org/dev/peps/pep-0484/
.. _PEP-526: https://www.python.org/dev/peps/pep-0526/
