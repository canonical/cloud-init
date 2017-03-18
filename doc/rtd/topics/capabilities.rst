************
Capabilities
************

- Setting a default locale
- Setting a instance hostname
- Generating instance ssh private keys
- Adding ssh keys to a users ``.ssh/authorized_keys`` so they can log in
- Setting up ephemeral mount points
- Configuring network devices

User configurability
====================

`Cloud-init`_ 's behavior can be configured via user-data.

    User-data can be given by the user at instance launch time.

This is done via the ``--user-data`` or ``--user-data-file`` argument to
ec2-run-instances for example.

* Check your local clients documentation for how to provide a `user-data`
  string or `user-data` file for usage by cloud-init on instance creation.


Feature detection
=================

Newer versions of cloud-init may have a list of additional features that they
support. This allows other applications to detect what features the installed
cloud-init supports without having to parse its version number. If present,
this list of features will be located at ``cloudinit.version.FEATURES``.

When checking if cloud-init supports a feature, in order to not break the
detection script on older versions of cloud-init without the features list, a
script similar to the following should be used. Note that this will exit 0 if
the feature is supported and 1 otherwise::

    import sys
    from cloudinit import version
    sys.exit('<FEATURE_NAME>' not in getattr(version, 'FEATURES', []))

Currently defined feature names include:

 - ``NETWORK_CONFIG_V1`` support for v1 networking configuration, see curtin
   documentation for examples.

.. _Cloud-init: https://launchpad.net/cloud-init
.. vi: textwidth=78
