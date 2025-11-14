Contribute to the code
**********************

.. toctree::
   :maxdepth: 1
   :hidden:

   testing.rst
   integration_tests.rst
   module_creation.rst
   datasource_creation.rst
   dir_layout.rst
   logging.rst
   internal_files.rst
   feature_flags.rst

For a run-through of the entire process, the following pages will be your best
starting point:

* :doc:`Find issues to work on<find_issues>`
* :doc:`Create your first pull request<first_PR>`

On the rest of this page you'll find the key resources you'll need to start
contributing to the cloud-init codebase.

Code style and design
=====================

Cloud-init adheres to `PEP 8`_, and this is enforced by our use of ``black``,
``isort`` and ``ruff``.

Python support
--------------

Cloud-init upstream currently supports Python 3.8 and above.

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
   * - 24.3
     - 3.8+
   * - 22.1
     - 3.6+
   * - 20.3
     - 3.5+
   * - 19.4
     - 2.7+

.. LINKS:
.. include:: ../links.txt
.. _PEP 8: https://peps.python.org/pep-0008/
