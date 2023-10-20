Contribute to the code
**********************

For a run-through of the entire process, the following pages will be your best
starting point:

* :doc:`Find issues to work on<find_issues>`
* :doc:`Build your first pull request<first_PR>`
* :doc:`Our code review process<code_review>`

On the rest of this page you'll find the key resources you'll need to start
contributing to the cloud-init codebase.

Testing
=======

Submissions to cloud-init must include testing. Unit testing and integration
testing are integral parts of contributing code.

.. toctree::
   :maxdepth: 1
   :hidden:

   testing.rst
   integration_tests.rst

* :doc:`Unit testing overview and design principles<testing>`
* :doc:`Integration testing<integration_tests>`

Popular contributions
=====================

.. toctree::
   :maxdepth: 1
   :hidden:

   module_creation.rst
   datasource_creation.rst

The two most popular contributions we receive are new cloud config
:doc:`modules <module_creation>` and new
:doc:`datasources <datasource_creation>`; these pages will provide instructions
on how to create them.

Note that any new modules should use underscores in any new config options and
not hyphens (e.g. ``new_option`` and *not* ``new-option``).

Code style and design
=====================

We generally adhere to `PEP 8`_, and this is enforced by our use of ``black``,
``isort`` and ``ruff``.

Python support
--------------

Cloud-init upstream currently supports Python 3.6 and above.

Cloud-init upstream will stay compatible with a particular Python version for 6
years after release. After 6 years, we will stop testing upstream changes
against the unsupported version of Python and may introduce breaking changes.
This policy may change as needed.

The following table lists the cloud-init versions in which the minimum Python
version changed:

.. list-table::
   :header-rows: 1
   :align: center

   * - Cloud-init version
     - Python version
   * - 22.1
     - 3.6+
   * - 20.3
     - 3.5+
   * - 19.4
     - 2.7+

Type annotations
----------------

The cloud-init codebase uses Python's annotation support for storing type
annotations in the style specified by `PEP-484`_ and `PEP-526`_. Their use in
the codebase is encouraged.

Other resources
===============

.. toctree::
   :maxdepth: 1
   :hidden:

   dir_layout.rst

* :doc:`Explanation of the directory structure<dir_layout>`

Feature flags
-------------

.. automodule:: cloudinit.features
   :members:

.. LINKS:
.. include:: ../links.txt
.. _quickstart documentation: https://docs.github.com/en/get-started/quickstart
.. _tools/.github-cla-signers: https://github.com/canonical/cloud-init/blob/main/tools/.github-cla-signers
.. _repository: https://github.com/canonical/cloud-init
.. _contributor-agreement-canonical: https://launchpad.net/%7Econtributor-agreement-canonical/+members
.. _PR #344: https://github.com/canonical/cloud-init/pull/344
.. _PR #345: https://github.com/canonical/cloud-init/pull/345
.. _PEP-484: https://www.python.org/dev/peps/pep-0484/
.. _PEP-526: https://www.python.org/dev/peps/pep-0526/
.. _PEP 8: https://peps.python.org/pep-0008/
