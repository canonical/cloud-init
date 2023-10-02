Submit your first pull request
******************************

Follow these steps prior to submitting  your first pull request to cloud-init:

Setup Git and GitHub appropriately
==================================

Understanding how to use Git and GitHub is a prerequisite for contributing to
cloud-init. Please refer to the `GitHub quickstart`_ documentation
for more information.

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

Add your name to the CLA signers list
=====================================

As part of your first PR to cloud-init, you should also add your GitHub
username (alphabetically) to the in-repository list that we use to track CLA
signatures: `tools/.github-cla-signers`_.

`PR #344`_ and `PR #345`_ are good examples of what this should look like in
your pull request, though please do not use a separate PR for this step.

Create a sandbox environment
============================

It is very often helpful to create a safe and sandboxed environment to test
your changes in while you work. If you are not sure how to do this, check out
:ref:`our QEMU tutorial<tutorial_qemu>`, which walks through this process
step-by-step.

Format the code
===============

Apply the ``black`` and ``isort`` formatting rules with `tox`_: ::

    tox -e do_format

Run unit tests
==============

Run unit tests and lint/formatting checks with `tox`_: ::

    tox

Read our code review process
============================

Once you have submitted your PR (if not earlier!) you will want to read the
cloud-init :ref:`Code Review Process<code_review_process>`, so you can
understand how your changes will end up in cloud-init's codebase.

.. include:: ../links.txt
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
