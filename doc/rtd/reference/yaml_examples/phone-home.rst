.. _cce-phone-home:

Phone home: post data to remote host
************************************

For a full list of keys, refer to the `phone home module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    phone_home:
        url: http://example.com/$INSTANCE_ID/
        post: all

Example 2
=========

.. code-block:: yaml

    #cloud-config
    phone_home:
        url: http://example.com/$INSTANCE_ID/
        post:
            - pub_key_rsa
            - pub_key_ecdsa
            - pub_key_ed25519
            - instance_id
            - hostname
            - fqdn
        tries: 5

.. LINKS
.. _phone home module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#byobu
