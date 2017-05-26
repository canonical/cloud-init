.. _datasource_config_drive:

Config Drive
============

The configuration drive datasource supports the `OpenStack`_ configuration
drive disk.

  See `the config drive extension`_ and `introduction`_ in the public
  documentation for more information.

By default, cloud-init does *always* consider this source to be a full-fledged
datasource.  Instead, the typical behavior is to assume it is really only
present to provide networking information.  Cloud-init will copy off the
network information, apply it to the system, and then continue on.  The "full"
datasource could then be found in the EC2 metadata service. If this is not the
case then the files contained on the located drive must provide equivalents to
what the EC2 metadata service would provide (which is typical of the version 2
support listed below)

Version 1
---------
**Note:** Version 1 is legacy and should be considered deprecated.  Version 2
has been supported in OpenStack since 2012.2 (Folsom).

The following criteria are required to as a config drive:

1. Must be formatted with `vfat`_ filesystem
2. Must contain *one* of the following files

::

  /etc/network/interfaces
  /root/.ssh/authorized_keys
  /meta.js

``/etc/network/interfaces``

    This file is laid down by nova in order to pass static networking
    information to the guest.  Cloud-init will copy it off of the config-drive
    and into /etc/network/interfaces (or convert it to RH format) as soon as
    it can, and then attempt to bring up all network interfaces.

``/root/.ssh/authorized_keys``

    This file is laid down by nova, and contains the ssk keys that were
    provided to nova on instance creation (nova-boot --key ....)

``/meta.js``

    meta.js is populated on the config-drive in response to the user passing
    "meta flags" (nova boot --meta key=value ...). It is expected to be json
    formatted.

Version 2
---------

The following criteria are required to as a config drive:

1. Must be formatted with `vfat`_ or `iso9660`_ filesystem
   or have a *filesystem* label of **config-2**
2. The files that will typically be present in the config drive are:

::

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
---------------

Cloud-init's behavior can be modified by keys found in the meta.js (version 1
only) file in the following ways.

::

   dsmode:  
     values: local, net, pass
     default: pass


This is what indicates if configdrive is a final data source or not.
By default it is 'pass', meaning this datasource should not be read.
Set it to 'local' or 'net' to stop cloud-init from continuing on to
search for other data sources after network config.

The difference between 'local' and 'net' is that local will not require
networking to be up before user-data actions (or boothooks) are run.

::
    
   instance-id:
     default: iid-dsconfigdrive
     
This is utilized as the metadata's instance-id.  It should generally
be unique, as it is what is used to determine "is this a new instance".

::

   public-keys:
     default: None
  
If present, these keys will be used as the public keys for the
instance.  This value overrides the content in authorized_keys.

Note: it is likely preferable to provide keys via user-data

::
    
   user-data:
     default: None
     
This provides cloud-init user-data. See :ref:`examples <yaml_examples>` for 
what all can be present here.

.. _OpenStack: http://www.openstack.org/
.. _introduction: http://docs.openstack.org/trunk/openstack-compute/admin/content/config-drive.html
.. _python-novaclient: https://github.com/openstack/python-novaclient
.. _iso9660: https://en.wikipedia.org/wiki/ISO_9660
.. _vfat: https://en.wikipedia.org/wiki/File_Allocation_Table
.. _the config drive extension: http://docs.openstack.org/user-guide/content/config-drive.html
.. vi: textwidth=78
