.. _cce-salt-minion:

Salt minion
***********

For a full list of keys, refer to the `Salt minion module` schema.

.. code-block:: yaml

    #cloud-config
    salt_minion:
        pkg_name: salt-minion
        service_name: salt-minion
        config_dir: /etc/salt
        conf:
            file_client: local
            fileserver_backend:
              - gitfs
            gitfs_remotes:
              - https://github.com/_user_/_repo_.git
            master: salt.example.com
        grains:
            role:
                - web
        public_key: |
            ------BEGIN PUBLIC KEY-------
            <key data>
            ------END PUBLIC KEY-------
        private_key: |
            ------BEGIN PRIVATE KEY------
            <key data>
            ------END PRIVATE KEY-------
        pki_dir: /etc/salt/pki/minion

.. LINKS
.. _Salt minion module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#salt-minion
