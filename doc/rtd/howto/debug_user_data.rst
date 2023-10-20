How to debug user data
======================

Two of the most common issues with cloud config user data are:

1. Incorrectly formatted YAML
2. The first line does not contain ``#cloud-config``

Static user data validation
---------------------------

To verify your cloud config is valid YAML you can use `validate-yaml.py`_.

To ensure the keys and values in your user data are correct, you can run:

.. code-block:: shell-session

   sudo cloud-init schema --system --annotate

Or, to test YAML in a file:

.. code-block:: shell-session

   cloud-init schema -c test.yml --annotate

Log analysis
------------

If you can log into your system, the best way to debug your system is to
check the contents of the log files :file:`/var/log/cloud-init.log` and
:file:`/var/log/cloud-init-output.log` for warnings, errors, and
tracebacks. Tracebacks are always reportable bugs.

To report any bugs you find, :ref:`refer to this guide <reporting_bugs>`.

Validation service
------------------

Another option to is to use the self-hosted HTTP `validation service`_,
refer to its documentation for more info.

.. LINKS
.. _validate-yaml.py: https://github.com/canonical/cloud-init/blob/main/tools/validate-yaml.py
.. _validation service: https://github.com/aciba90/cloud-config-validator
