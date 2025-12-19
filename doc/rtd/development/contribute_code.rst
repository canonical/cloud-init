Contribute to the code
**********************

.. toctree::
   :maxdepth: 1
   :hidden:

   About the tests <testing.rst>
   Support a new cloud <datasource_creation.rst>
   Run integration tests <integration_tests.rst>
   Extend cloud-config <module_creation.rst>
   Find bugs to fix <find_issues.rst>

Code style and design
=====================

Cloud-init adheres to `PEP 8`_, and this is enforced by CI tests.

Python support
--------------

Cloud-init upstream currently supports Python 3.9 and above.

Cloud-init upstream will stay compatible with a particular Python version for 6
years after release. After that, upstream will stop testing upstream changes
against the unsupported version of Python and may introduce breaking changes.

The following table lists the cloud-init versions in which the minimum Python
version changed:

.. list-table::
   :header-rows: 1
   :align: center

   * - Cloud-init version
     - Python version
   * - 25.4
     - 3.9+
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
