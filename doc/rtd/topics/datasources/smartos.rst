.. _datasource_smartos:

SmartOS Datasource
==================

This datasource finds metadata and user-data from the SmartOS virtualization
platform (i.e. Joyent).

Please see http://smartos.org/ for information about SmartOS.

SmartOS Platform
----------------
The SmartOS virtualization platform uses meta-data to the instance via the
second serial console. On Linux, this is /dev/ttyS1. The data is a provided
via a simple protocol: something queries for the data, the console responds
responds with the status and if "SUCCESS" returns until a single ".\n".

New versions of the SmartOS tooling will include support for base64 encoded data.

Meta-data channels
------------------

Cloud-init supports three modes of delivering user/meta-data via the flexible
channels of SmartOS.

* user-data is written to /var/db/user-data

  - per the spec, user-data is for consumption by the end-user, not
    provisioning tools
  - cloud-init entirely ignores this channel other than writting it to disk
  - removal of the meta-data key means that /var/db/user-data gets removed
  - a backup of previous meta-data is maintained as
    /var/db/user-data.<timestamp>. <timestamp> is the epoch time when
    cloud-init ran

* user-script is written to /var/lib/cloud/scripts/per-boot/99_user_data

  - this is executed each boot
  - a link is created to /var/db/user-script
  - previous versions of the user-script is written to
    /var/lib/cloud/scripts/per-boot.backup/99_user_script.<timestamp>.
    - <timestamp> is the epoch time when cloud-init ran.
  - when the 'user-script' meta-data key goes missing, the user-script is
    removed from the file system, although a backup is maintained.
  - if the script is not shebanged (i.e. starts with #!<executable>), then
    or is not an executable, cloud-init will add a shebang of "#!/bin/bash"

* cloud-init:user-data is treated like on other Clouds.

  - this channel is used for delivering _all_ cloud-init instructions
  - scripts delivered over this channel must be well formed (i.e. must have
    a shebang)

Cloud-init supports reading the traditional meta-data fields supported by the
SmartOS tools. These are:

 * root_authorized_keys
 * hostname
 * enable_motd_sys_info
 * iptables_disable

Note: At this time iptables_disable and enable_motd_sys_info are read but
    are not actioned.

Disabling user-script
---------------------

Cloud-init uses the per-boot script functionality to handle the execution
of the user-script.  If you want to prevent this use a cloud-config of:

.. code:: yaml

  #cloud-config
  cloud_final_modules:
   - scripts-per-once
   - scripts-per-instance
   - scripts-user
   - ssh-authkey-fingerprints
   - keys-to-console
   - phone-home
   - final-message
   - power-state-change

Alternatively you can use the json patch method

.. code:: yaml

  #cloud-config-jsonp
  [
       { "op": "replace",
         "path": "/cloud_final_modules",
         "value": ["scripts-per-once",
                   "scripts-per-instance",
                   "scripts-user",
                   "ssh-authkey-fingerprints",
                   "keys-to-console",
                   "phone-home",
                   "final-message",
                   "power-state-change"]
       }
  ]

The default cloud-config includes "script-per-boot". Cloud-init will still
ingest and write the user-data but will not execute it, when you disable
the per-boot script handling.

Note: Unless you have an explicit use-case, it is recommended that you not
        disable the per-boot script execution, especially if you are using
        any of the life-cycle management features of SmartOS.

The cloud-config needs to be delivered over the cloud-init:user-data channel
in order for cloud-init to ingest it.

base64
------

The following are exempt from base64 encoding, owing to the fact that they
are provided by SmartOS:

 * root_authorized_keys
 * enable_motd_sys_info
 * iptables_disable
 * user-data
 * user-script

This list can be changed through system config of variable 'no_base64_decode'.

This means that user-script and user-data as well as other values can be
base64 encoded. Since Cloud-init can only guess as to whether or not something
is truly base64 encoded, the following meta-data keys are hints as to whether
or not to base64 decode something:

  * base64_all: Except for excluded keys, attempt to base64 decode
    the values. If the value fails to decode properly, it will be
    returned in its text
  * base64_keys: A comma deliminated list of which keys are base64 encoded.
  * b64-<key>:
    for any key, if there exists an entry in the metadata for 'b64-<key>'
    Then 'b64-<key>' is expected to be a plaintext boolean indicating whether
    or not its value is encoded.
  * no_base64_decode: This is a configuration setting
    (i.e. /etc/cloud/cloud.cfg.d) that sets which values should not be
    base64 decoded.

disk_aliases and ephemeral disk
-------------------------------
By default, SmartOS only supports a single ephemeral disk.  That disk is
completely empty (un-partitioned with no filesystem).

The SmartOS datasource has built-in cloud-config which instructs the
'disk_setup' module to partition and format the ephemeral disk.

You can control the disk_setup then in 2 ways:
 1. through the datasource config, you can change the 'alias' of
    ephermeral0 to reference another device. The default is:

      'disk_aliases': {'ephemeral0': '/dev/vdb'},

    Which means anywhere disk_setup sees a device named 'ephemeral0'
    then /dev/vdb will be substituted.
 2. you can provide disk_setup or fs_setup data in user-data to overwrite
    the datasource's built-in values.

See doc/examples/cloud-config-disk-setup.txt for information on disk_setup.

.. vi: textwidth=78
