==================
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

Userdata
--------

In SmartOS parlance, user-data is a actually meta-data. This userdata can be
provided as key-value pairs.

Cloud-init supports reading the traditional meta-data fields supported by the
SmartOS tools. These are:
 * root_authorized_keys
 * hostname
 * enable_motd_sys_info
 * iptables_disable

Note: At this time iptables_disable and enable_motd_sys_info are read but
    are not actioned.

user-script
-----------

SmartOS traditionally supports sending over a user-script for execution at the
rc.local level. Cloud-init supports running user-scripts as if they were
cloud-init user-data. In this sense, anything with a shell interpreter
directive will run.

user-data and user-script
-------------------------

In the event that a user defines the meta-data key of "user-data" it will
always supersede any user-script data. This is for consistency.

base64
------

The following are exempt from base64 encoding, owing to the fact that they
are provided by SmartOS:
 * root_authorized_keys
 * enable_motd_sys_info
 * iptables_disable

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

disk_aliases and ephemeral disk:
---------------
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
