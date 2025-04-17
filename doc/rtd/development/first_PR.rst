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
`contributor license agreement <CLA_>`_ (CLA). A check is run against
every pull request to ensure that the CLA has been signed.

For any questions or help with the process, email
`James Falcon <mailto:james.falcon@canonical.com>`_ with the subject:
"Cloud-init CLA". You can also contact user ``falcojr`` in the #cloud-init
channel on the `Libera IRC network <IRC_>`_.

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
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
