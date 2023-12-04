.. _check_user_data_cloud_config:

How to validate user data cloud config
======================================

The two most common issues with cloud config user data are:

1. Incorrectly formatted YAML
2. The first line does not start with ``#cloud-config``

Static user data validation
---------------------------

Cloud-init is capable of validating cloud config user data directly from
its datasource (i.e. on a running cloud instance). To do this, you can run:

.. code-block:: shell-session

   sudo cloud-init schema --system --annotate

Or, to test YAML in a specific file:

.. code-block:: shell-session

   cloud-init schema -c test.yml --annotate

Example output:

.. code-block:: shell-session

    $ cloud-init schema --config-file=test.yaml --annotate
    #cloud-config
    users:
      - name: holmanb        # E1,E2,E3
        gecos: Brett Holman
        primary_group: holmanb
        lock_passwd: false
        invalid_key: true

    # Errors: -------------
    # E1: Additional properties are not allowed ('invalid_key' was unexpected)
    # E2: {'name': 'holmanb', 'gecos': 'Brett Holman', 'primary_group': 'holmanb', 'lock_passwd': False, 'invalid_key': True} is not of type 'array'
    # E3: {'name': 'holmanb', 'gecos': 'Brett Holman', 'primary_group': 'holmanb', 'lock_passwd': False, 'invalid_key': True} is not of type 'string'

Debugging
---------

If your user-data cloud config is correct according to the `cloud-init schema`
command, but you are still having issues, then please refer to our
:ref:`debugging guide<how_to_debug>`.

To report any bugs you find, :ref:`refer to this guide <reporting_bugs>`.

.. LINKS
.. _validate-yaml.py: https://github.com/canonical/cloud-init/blob/main/tools/validate-yaml.py
.. _validation service: https://github.com/aciba90/cloud-config-validator
