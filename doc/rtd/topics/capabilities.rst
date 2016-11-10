************
Capabilities
************

- Setting a default locale
- Setting a instance hostname
- Generating instance ssh private keys
- Adding ssh keys to a users ``.ssh/authorized_keys`` so they can log in
- Setting up ephemeral mount points

User configurability
====================

`Cloud-init`_ 's behavior can be configured via user-data.

    User-data can be given by the user at instance launch time.

This is done via the ``--user-data`` or ``--user-data-file`` argument to
ec2-run-instances for example.

* Check your local clients documentation for how to provide a `user-data`
  string or `user-data` file for usage by cloud-init on instance creation.


.. _Cloud-init: https://launchpad.net/cloud-init
.. vi: textwidth=78
