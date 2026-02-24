.. _datasource_smartos:

SmartOS Datasource
******************

This datasource finds meta-data and user-data from the SmartOS virtualization
platform (i.e., Joyent).

Please see http://smartos.org/ for information about SmartOS.

SmartOS platform
================

The SmartOS virtualization platform uses instance-data from the instance via
the second serial console. On Linux, this is :file:`/dev/ttyS1`. The data is
provided via a simple protocol:

* Something queries for the data,
* the console responds with the status, and
* if "SUCCESS" returns until a single ".\n".

New versions of the SmartOS tooling will include support for Base64-encoded
data.

Instance metadata channels
==========================

``Cloud-init`` supports three modes of delivering configuration data via
the flexible channels of SmartOS.

1. User-data is written to :file:`/var/db/user-data`:

   - As per the spec, user-data is for consumption by the end user, not
     provisioning tools.
   - ``Cloud-init`` ignores this channel, other than writing it to disk.
   - Removal of the ``meta-data`` key means that :file:`/var/db/user-data`
     gets removed.
   - A backup of previous meta-data is maintained as
     :file:`/var/db/user-data.<timestamp>`. ``<timestamp>`` is the epoch time
     when ``cloud-init`` ran.

2. ``user-script`` is written to
   :file:`/var/lib/cloud/scripts/per-boot/99_user_data`:

   - This is executed each boot.
   - A link is created to :file:`/var/db/user-script`.
   - Previous versions of ``user-script`` are written to
     :file:`/var/lib/cloud/scripts/per-boot.backup/99_user_script.<timestamp>.`
   - <timestamp> is the epoch time when ``cloud-init`` ran.
   - When the ``user-script`` meta-data key goes missing, ``user-script`` is
     removed from the file system, although a backup is maintained.
   - If the script does not start with a shebang (i.e., it starts with
     #!<executable>), or it is not an executable, ``cloud-init`` will add a
     shebang of "#!/bin/bash".

3. ``Cloud-init`` user-data is treated like on other Clouds.

   - This channel is used for delivering all ``cloud-init`` instructions.
   - Scripts delivered over this channel must be well formed (i.e., they must
     have a shebang).

``Cloud-init`` supports reading the traditional ``meta-data`` fields supported
by the SmartOS tools. These are:

* ``root_authorized_keys``
* ``hostname``
* ``enable_motd_sys_info``
* ``iptables_disable``

.. note::
   At this time, ``iptables_disable`` and ``enable_motd_sys_info`` are read
   but are not actioned.

Disabling ``user-script``
=========================

``Cloud-init`` uses the per-boot script functionality to handle the execution
of the ``user-script``. If you want to prevent this, use a cloud-config of:

.. code-block:: yaml

   #cloud-config
   cloud_final_modules:
    - scripts_per_once
    - scripts_per_instance
    - scripts_user
    - ssh_authkey_fingerprints
    - keys_to_console
    - phone_home
    - final_message
    - power_state_change

Alternatively you can use the JSON patch method:

.. code-block:: yaml

   #cloud-config-jsonp
   [
        { "op": "replace",
          "path": "/cloud_final_modules",
          "value": ["scripts_per_once",
                    "scripts_per_instance",
                    "scripts_user",
                    "ssh_authkey_fingerprints",
                    "keys_to_console",
                    "phone_home",
                    "final_message",
                    "power_state_change"]
        }
   ]

The default cloud-config includes "script-per-boot". ``Cloud-init`` will still
ingest and write the user-data, but will not execute it when you disable
the per-boot script handling.

The cloud-config needs to be delivered over the ``cloud-init:user-data``
channel in order for ``cloud-init`` to ingest it.

.. note::
   Unless you have an explicit use-case, it is recommended that you do not
   disable the per-boot script execution, especially if you are using
   any of the life-cycle management features of SmartOS.

Base64
======

The following are exempt from Base64 encoding, owing to the fact that they
are provided by SmartOS:

* ``root_authorized_keys``
* ``enable_motd_sys_info``
* ``iptables_disable``
* ``user-data``
* ``user-script``

This list can be changed through the
:ref:`datasource base configuration<base_config-Datasource>` variable
``no_base64_decode``.

This means that ``user-script``, ``user-data`` and other values can be Base64
encoded. Since ``cloud-init`` can only guess whether or not something
is truly Base64 encoded, the following meta-data keys are hints as to whether
or not to Base64 decode something:

* ``base64_all``: Except for excluded keys, attempt to Base64 decode the
  values. If the value fails to decode properly, it will be returned in its
  text.
* ``base64_keys``: A comma-delimited list of which keys are Base64 encoded.
* ``b64-<key>``: For any key, if an entry exists in the meta-data for
  ``'b64-<key>'``, then ``'b64-<key>'`` is expected to be a plaintext boolean
  indicating whether or not its value is encoded.
* ``no_base64_decode``: This is a configuration setting
  (i.e., :file:`/etc/cloud/cloud.cfg.d`) that sets which values should not
  be Base64 decoded.

``disk_aliases`` and ephemeral disk
===================================

By default, SmartOS only supports a single ephemeral disk. That disk is
completely empty (unpartitioned, with no filesystem).

The SmartOS datasource has built-in cloud-config which instructs the
``disk_setup`` module to partition and format the ephemeral disk.

You can control the ``disk_setup`` in 2 ways:

1. Through the datasource config, you can change the 'alias' of ``ephemeral0``
   to reference another device. The default is:

   .. code-block::

      'disk_aliases': {'ephemeral0': '/dev/vdb'}

   This means that anywhere ``disk_setup`` sees a device named 'ephemeral0',
   then :file:`/dev/vdb` will be substituted.

2. You can provide ``disk_setup`` or ``fs_setup`` data in ``user-data`` to
   overwrite the datasource's built-in values.

See :file:`doc/examples/cloud-config-disk-setup.txt` for information on
``disk_setup``.
