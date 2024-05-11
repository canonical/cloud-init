.. _cce-redhat-subscription:

Register a Red Hat system
*************************

For a full list of keys, refer to the `Red Hat subscription module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    rh_subscription:
        username: joe@foo.bar
        ## Quote your password if it has symbols to be safe
        password: '1234abcd'

Example 2
=========

.. code-block:: yaml

    #cloud-config
    rh_subscription:
        activation-key: foobar
        org: 12345

Example 3
=========

.. code-block:: yaml

    #cloud-config
    rh_subscription:
        activation-key: foobar
        org: 12345
        auto-attach: true
        service-level: self-support
        add-pool:
          - 1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a
          - 2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b
        enable-repo:
          - repo-id-to-enable
          - other-repo-id-to-enable
        disable-repo:
          - repo-id-to-disable
          - other-repo-id-to-disable
        # Alter the baseurl in /etc/rhsm/rhsm.conf
        rhsm-baseurl: http://url
        # Alter the server hostname in /etc/rhsm/rhsm.conf
        server-hostname: foo.bar.com

.. LINKS
.. _Red Hat subscription module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#red-hat-subscription
