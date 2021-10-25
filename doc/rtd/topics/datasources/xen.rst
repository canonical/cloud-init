.. _datasource_xen:

Xen
======

This datasource is for the use with XCP-ng/ Xen platforms reads vendor, metadata and user data from
Xenstore


Configuration
-------------

The configuration method is dependent upon the transport:

Xenstore Keys
^^^^^^^^^^^^^^

One method of providing meta, user, and vendor data is by setting the following
key/value pairs on a VM's Xenstore:

.. list-table::
   :header-rows: 1

   * - Property
     - Description
   * - ``vm-data/metadata``
     - A YAML or JSON document containing the cloud-init metadata.
   * - ``vm-data/metadata/encoding``
     - The encoding type for ``vm-data/metadata``.
   * - ``vm-data/userdata``
     - A YAML document containing the cloud-init user data.
   * - ``vm-data/userdata/encoding``
     - The encoding type for ``vm-data/userdata``.
   * - ``vm-data/vendordata``
     - A YAML document containing the cloud-init vendor data.
   * - ``vm-data/vendordata/encoding``
     - The encoding type for ``vm-data/vendordata``.


All ``vm-data/*/encoding`` values may be set to ``base64`` or
``gzip+base64``.

Features
--------

This section reviews several features available in this datasource, regardless
of how the meta, user, and vendor data was discovered.

Instance data and lazy networks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One of the hallmarks of cloud-init is `its use of instance-data and JINJA
queries <../instancedata.html#using-instance-data>`_
-- the ability to write queries in user and vendor data that reference runtime
information present in ``/run/cloud-init/instance-data.json``. This works well
when the metadata provides all of the information up front, such as the network
configuration. For systems that rely on DHCP, however, this information may not
be available when the metadata is persisted to disk.

This datasource ensures that even if the instance is using DHCP to configure
networking, the same details about the configured network are available in
``/run/cloud-init/instance-data.json`` as if static networking was used. This
information collected at runtime is easy to demonstrate by executing the
datasource on the command line. From the root of this repository, run the
following command:

.. code-block:: bash

   PYTHONPATH="$(pwd)" python3 cloudinit/sources/DataSourceVMware.py

The above command will result in output similar to the below JSON:

.. code-block:: json

   {
       "hostname": "kalpesh.localhost",
       "local-hostname": "kalpesh.localhost",
       "local-ipv4": "10.10.8.15",
       "local_hostname": "kalpesh.localhost",
       "network": {
           "config": {
               "dhcp": true
           },
           "interfaces": {
               "by-ipv4": {
                   "172.0.0.2": {
                       "netmask": "255.255.255.255",
                       "peer": "172.0.0.2"
                   },
                   "192.168.0.188": {
                       "broadcast": "192.168.0.255",
                       "mac": "64:4b:f0:18:9a:21",
                       "netmask": "255.255.255.0"
                   }
               },
               "by-ipv6": {
                   "fd8e:d25e:c5b6:1:1f5:b2fd:8973:22f2": {
                       "flags": 208,
                       "mac": "64:4b:f0:18:9a:21",
                       "netmask": "ffff:ffff:ffff:ffff::/64"
                   }
               },
               "by-mac": {
                   "64:4b:f0:18:9a:21": {
                       "ipv4": [
                           {
                               "addr": "192.168.0.188",
                               "broadcast": "192.168.0.255",
                               "netmask": "255.255.255.0"
                           }
                       ],
                       "ipv6": [
                           {
                               "addr": "fd8e:d25e:c5b6:1:1f5:b2fd:8973:22f2",
                               "flags": 208,
                               "netmask": "ffff:ffff:ffff:ffff::/64"
                           }
                       ]
                   },
                   "ac:de:48:00:11:22": {
                       "ipv6": []
                   }
               }
           }
       },
       "wait-on-network": {
           "ipv4": true,
           "ipv6": "false"
       }
   }

Reading the local IP addresses
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This datasource automatically discovers the local IPv4 and IPv6 addresses for
a guest operating system based on the default routes. However, when inspecting
a VM externally, it's not possible to know what the *default* IP address is for
the guest OS. That's why this datasource sets the discovered, local IPv4 and
IPv6 addresses back in the guestinfo namespace as the following keys:


* ``vm-data/local-ipv4``
* ``vm-data/local-ipv6``

It is possible that a host may not have any default, local IP addresses. It's
also possible the reported, local addresses are link-local addresses. But these
two keys may be used to discover what this datasource determined were the local
IPv4 and IPv6 addresses for a host.

Waiting on the network
^^^^^^^^^^^^^^^^^^^^^^

Sometimes cloud-init may bring up the network, but it will not finish coming
online before the datasource's ``setup`` function is called, resulting in an
``/var/run/cloud-init/instance-data.json`` file that does not have the correct
network information. It is possible to instruct the datasource to wait until an
IPv4 or IPv6 address is available before writing the instance data with the
following metadata properties:

.. code-block:: yaml

   wait-on-network:
     ipv4: true
     ipv6: true

If either of the above values are true, then the datasource will sleep for a
second, check the network status, and repeat until one or both addresses from
the specified families are available.

Walkthrough
-----------

The following series of steps is a demonstration on how to configure a VM with
this datasource:


#. Create the metadata file for the VM. Save the following YAML to a file named
   ``metadata.yaml``\ :

   .. code-block:: yaml

        instance-id: {VM_Name}
        local-hostname: "vmsvc-cloudinit-0"
        network:
        version: 2
        ethernets:
            ens192:
            addresses: [10.12.6.181/24]
            gateway4: 10.12.6.1
            dhcp6: false
            nameservers:
                addresses:
                - 8.8.8.8
                search:
                - search.local
            dhcp4: false
            optional: true


#. Create the userdata file ``userdata.yaml``\ :

   .. code-block:: yaml

        #cloud-config
        #This is example configuration. We can create according to need
        users:
        - default
        
        - name: kalpesh
            gecos: Kalpesh Gade
            #To disable password login (It allows only SSH key based login )
            lock_passwd: false
            hashed_passwd: <SHA512 encoded passwd with rounds 4096>
            #To copy SSH keys to ~/.ssh/authorized_keys
            ssh_authorized_keys:
                - ssh-rsa <SSH KEYS>
            #Unrestricted Sudo access
            sudo: ALL=(ALL) NOPASSWD:ALL
            #To allow SSH Password Authentication
            ssh_pwauth: True


#. Please note this step requires that the VM be powered off. 

     xe vm-export -h hostname -u root -pw password vm=vm_name \
    filename=pathname_of_file

#. Power off the VM:

   .. raw:: html

      <hr />

      &#x26a0;&#xfe0f; <strong>First Boot Mode</strong>

   To ensure the next power-on operation results in a first-boot scenario for
   cloud-init, it may be necessary to run the following command just before
   powering off the VM:

   .. code-block:: bash

      cloud-init clean

   Otherwise cloud-init may not run in first-boot mode. For more information
   on how the boot mode is determined, please see the
   `First Boot Documentation <../boot.html#first-boot-determination>`_.
   .. code-block:: bash

      xe vm-shutdown uuid=<UUID of VM> force=true    


#.
   Export the environment variables that contain the cloud-init metadata and
   userdata:

   .. code-block:: shell

      export METADATA=$(gzip -c9 <metadata.yaml | { base64 -w0 2>/dev/null || base64; }) \
           USERDATA=$(gzip -c9 <userdata.yaml | { base64 -w0 2>/dev/null || base64; })

#.
   Assign the metadata and userdata to the VM:

   .. code-block:: shell

        xe vm-param-set uuid=<new-vm-uuid> xenstore-data:vm-data/userdata=<userdata>
        xe vm-param-set uuid=<new-vm-uuid> xenstore-data:vm-data/metadata=<metadata>
        xe vm-param-set uuid=<new-vm-uuid> xenstore-data:vm-data/metadata/encoding=<enc_type>
        xe vm-param-set uuid=<new-vm-uuid> xenstore-data:vm-data/userdata/encoding=<enc_type>

   Please note the above commands include specifying the encoding for the
   properties. This is important as it informs the datasource how to decode
   the data for cloud-init. Valid values for ``metadata/encoding`` and
   ``userdata/encoding`` include:


   * ``base64``
   * ``gzip+base64``



If all went according to plan, the CentOS box is:

* Locked down, allowing SSH access only for the user in the userdata
* Configured for a dynamic IP address via DHCP
* Has a hostname of ``cloud-vm``

Examples
--------

This section reviews common configurations:

Setting the hostname
^^^^^^^^^^^^^^^^^^^^

The hostname is set by way of the metadata key ``local-hostname``.

Setting the instance ID
^^^^^^^^^^^^^^^^^^^^^^^

The instance ID may be set by way of the metadata key ``instance-id``. However,
if this value is absent then then the instance ID is read from the file
``/sys/class/dmi/id/product_uuid``.

Providing public SSH keys
^^^^^^^^^^^^^^^^^^^^^^^^^

The public SSH keys may be set by way of the metadata key ``public-keys-data``.
Each newline-terminated string will be interpreted as a separate SSH public
key, which will be placed in distro's default user's
``~/.ssh/authorized_keys``. If the value is empty or absent, then nothing will
be written to ``~/.ssh/authorized_keys``.

