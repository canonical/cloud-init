.. _contributing:

How to contribute to cloud-init
*******************************

Thank you for wanting to help us improve cloud-init! There are a variety of
ways you can contribute to this project, including no-code and low-code
options. This documentation will help orient you with our processes.

Please make sure that you read this guide before starting to contribute. It
contains all the details you need to know to give your contribution the best
chance of being accepted.

Cloud-init is hosted and managed on `GitHub`_. If you're not
familiar with how GitHub works, their
`quickstart documentation`_
provides an excellent introduction to all the tools and processes you'll need
to know.

.. _contributing-prerequisites:

Prerequisites
=============

Before you can begin, you will need to:

* Read and agree to abide by our `Code of Conduct`_.

* Sign the Canonical `contributor license agreement <CLA_>`_. This grants us your
  permission to use your contributions in the project.

* Create (or have) a GitHub account. We will refer to your GitHub username as
  ``GH_USER``.

Getting help
============

We use IRC and have a dedicated `#cloud-init` channel where you can contact
us for help and guidance. This link will take you directly to our
`IRC channel on Libera <IRC_>`_.

Getting started
===============

.. toctree::
    :maxdepth: 1

    find_issues.rst
    first_PR.rst
    code_review.rst

For existing contributors
=========================

Pull request checklist
----------------------

Before any pull request can be accepted, remember to do the following:

* Make sure your GitHub username is added (alphabetically) to the in-repository
  list that we use to track CLA signatures: `tools/.github-cla-signers`_.
* Add or update any :ref:`unit tests<testing>` accordingly.
* Add or update any :ref:`integration_tests` (if applicable).
* Format code (using ``black`` and ``isort``) with ``tox -e do_format``.
* Run unit tests and/or linting checks pass using ``tox``.
* Submit a PR against the ``main`` branch of the cloud-init repository.

Debugging and reporting
-----------------------

.. toctree::
   :maxdepth: 1

   ../howto/bugs.rst
   logging.rst
   debugging.rst

Transferring CLA Signatures from Launchpad to GitHub
----------------------------------------------------

If you signed the CLA in Launchpad before the GitHub username field was
included, we need to verify the link between your `Launchpad`_ account and
your `GitHub`_ account. To enable us to do this, we ask that you create a
branch with both your Launchpad and GitHub usernames against both the Launchpad
and GitHub cloud-init repositories. We've added a tool
(``tools/migrate-lp-user-to-github``) to the cloud-init repository to handle
this migration as automatically as possible.

The cloud-init team will review the two merge proposals, verify that the
CLA has been signed for the Launchpad user, and record the associated GitHub
account.

.. note::

   If you are a first time contributor, you will not need to do this. All new
   CLA signatures are handled as part of the GitHub pull request process when
   you make your first pull request.


.. LINKS:
.. include:: ../links.txt
.. _quickstart documentation: https://docs.github.com/en/get-started/quickstart
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _repository: https://github.com/canonical/cloud-init
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
.. _tox: https://tox.readthedocs.io/en/latest/
.. _PEP-484: https://www.python.org/dev/peps/pep-0484/
.. _PEP-526: https://www.python.org/dev/peps/pep-0526/
