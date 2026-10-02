.. _datasource_config_drive:

Config drive
************

The configuration drive datasource supports the `OpenStack`_ configuration
drive disk.

By default, ``cloud-init`` considers this source to be a fully-fledged
datasource: it reads the meta-data and user-data from the drive and stops
searching for other datasources. This is controlled by the ``dsmode`` key
described below, which defaults to ``net``.

A drive used this way must provide equivalents to what the EC2 instance
metadata service would provide, which is typical of the version 2 support
listed below.

.. note::
   See `the config drive extension`_ and `meta-data introduction`_ in the
   public documentation for more information.

.. dropdown:: Version 1 (deprecated)

   **Note: Version 1 is legacy and should be considered deprecated.
   Version 2 has been supported in OpenStack since 2012.2 (Folsom).**

   The following criteria are required to use a config drive:

        1. Must be formatted with `vfat`_ filesystem.
        2. Must contain *one* of the following files: ::

            /etc/network/interfaces
            /root/.ssh/authorized_keys
            /meta.js

        ``/etc/network/interfaces``

            This file is laid down by nova in order to pass static networking
            information to the guest. ``Cloud-init`` will copy it off of the
            config-drive and into /etc/network/interfaces (or convert it to RH
            format) as soon as it can, and then attempt to bring up all network
            interfaces.

        ``/root/.ssh/authorized_keys``

            This file is laid down by nova, and contains the ssk keys that were
            provided to nova on instance creation (nova-boot --key ....)

        ``/meta.js``

            meta.js is populated on the config-drive in response to the user
            passing "meta flags" (nova boot --meta key=value ...). It is
            expected to be json formatted.


Version 2
=========

The following criteria are required to use a config drive:

1. Must be formatted with `vfat`_ or `iso9660`_ filesystem, or have a
   *filesystem* label of ``config-2`` or ``CONFIG-2``.
2. The files that will typically be present in the config drive are: ::

    openstack/
      - 2012-08-10/ or latest/
        - meta_data.json
        - user_data (not mandatory)
      - content/
        - 0000 (referenced content files)
        - 0001
        - ....
    ec2
      - latest/
        - meta-data.json (not mandatory)

Keys and values
===============

``Cloud-init``'s behaviour can be modified by keys found in the
:file:`meta.js` (version 1 only) file in the following ways.

``dsmode``
----------

::

   dsmode:
     values: local, net, disabled
     default: net

This indicates whether the config drive is a final datasource, and at which
stage it is read. With the default of 'net', ``cloud-init`` reads the drive
and stops searching for other datasources.

The difference between 'local' and 'net' is that local will not require
networking to be up before user-data actions are run. Setting 'disabled'
stops the datasource from being used at all.

For a version 2 drive this key is read from the ``meta`` object in
:file:`meta_data.json`. For a version 1 drive it is read from
:file:`meta.js`. It can also be set in system configuration under
``datasource/ConfigDrive/dsmode``.

.. note::
   Earlier versions of this page listed a 'pass' value, described as
   applying only the networking information from the drive without
   claiming the datasource. ``cloud-init`` does not accept 'pass'. If it
   is supplied, a warning is logged and the default of 'net' is used.

``instance-id``
---------------

::

   instance-id:
     default: iid-dsconfigdrive

This is utilized as the meta-data's instance-id. It should generally
be unique, as it is what is used to determine "is this a new instance?".

``public-keys``
---------------

::

   public-keys:
     default: None

If present, these keys will be used as the public keys for the
instance. This value overrides the content in ``authorized_keys``.

.. note::
   It is likely preferable to provide keys via user-data.

``user-data``
-------------

::

   user-data:
     default: None

This provides ``cloud-init`` user-data. See :ref:`examples <yaml_examples>`
for details of what needs to be present here.

.. _OpenStack: http://www.openstack.org/
.. _meta-data introduction: https://docs.openstack.org/nova/latest/user/metadata.html#config-drives
.. _python-novaclient: https://github.com/openstack/python-novaclient
.. _iso9660: https://en.wikipedia.org/wiki/ISO_9660
.. _vfat: https://en.wikipedia.org/wiki/File_Allocation_Table
.. _the config drive extension: https://docs.openstack.org/nova/latest/admin/config-drive.html
