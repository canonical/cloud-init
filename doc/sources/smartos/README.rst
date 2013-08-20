==================
SmartOS Datasource
==================

This datasource finds metadata and user-data from the SmartOS virtualization
platform (i.e. Joyent).

SmartOS Platform
----------------
The SmartOS virtualization platform meta-data to the instance via the second
serial console. On Linux, this is /dev/ttyS1. The data is a provided via a
simple protocol, where something queries for the userdata, where the console
responds with the status and if "SUCCESS" returns until a single ".\n".

New versions of the SmartOS tooling will include support for base64 encoded data.

Userdata
--------

In SmartOS parlance, user-data is a actually meta-data. This userdata can be
provided a key-value pairs.

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
cloud-init user-data. In this sense, anything with a shell interpetter
directive will run

user-data and user-script
-------------------------

In the event that a user defines the meta-data key of "user-data" it will
always supercede any user-script data. This is for consistency.

base64
------

The following are excempt from base64 encoding, owing to the fact that they
are provided by SmartOS:
 * root_authorized_keys
 * enable_motd_sys_info
 * iptables_disable

This means that user-script and user-data as well as other values can be
base64 encoded. Since Cloud-init can only guess as to whether or not something
is truly base64 encoded, the following meta-data keys are hints as to whether
or not to base64 decode something:
  * decode_base64: Except for excluded keys, attempt to base64 decode
        the values. If the value fails to decode properly, it will be
        returned in its text
  * base_64_encoded: A comma deliminated list of which values are base64
        encoded.
  * no_base64_decode: This is a configuration setting (i.e. /etc/cloud/cloud.cfg.d)
        that sets which values should not be base64 decoded. 
