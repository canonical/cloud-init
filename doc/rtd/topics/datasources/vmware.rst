.. _datasource_vmware:

VMware
======

This datasource is for use with systems running on a VMware platform such as
vSphere and currently supports the following data transports:


* `GuestInfo <https://github.com/vmware/govmomi/blob/master/govc/USAGE.md#vmchange>`_ keys

Configuration
-------------

The configuration method is dependent upon the transport:

GuestInfo Keys
^^^^^^^^^^^^^^

One method of providing meta, user, and vendor data is by setting the following
key/value pairs on a VM's ``extraConfig`` `property <https://vdc-repo.vmware.com/vmwb-repository/dcr-public/723e7f8b-4f21-448b-a830-5f22fd931b01/5a8257bd-7f41-4423-9a73-03307535bd42/doc/vim.vm.ConfigInfo.html>`_:

.. list-table::
   :header-rows: 1

   * - Property
     - Description
   * - ``guestinfo.metadata``
     - A YAML or JSON document containing the cloud-init metadata.
   * - ``guestinfo.metadata.encoding``
     - The encoding type for ``guestinfo.metadata``.
   * - ``guestinfo.userdata``
     - A YAML document containing the cloud-init user data.
   * - ``guestinfo.userdata.encoding``
     - The encoding type for ``guestinfo.userdata``.
   * - ``guestinfo.vendordata``
     - A YAML document containing the cloud-init vendor data.
   * - ``guestinfo.vendordata.encoding``
     - The encoding type for ``guestinfo.vendordata``.


All ``guestinfo.*.encoding`` values may be set to ``base64`` or
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
       "hostname": "akutz.localhost",
       "local-hostname": "akutz.localhost",
       "local-ipv4": "192.168.0.188",
       "local_hostname": "akutz.localhost",
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


Redacting sensitive information
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes the cloud-init userdata might contain sensitive information, and it
may be desirable to have the ``guestinfo.userdata`` key (or other guestinfo
keys) redacted as soon as its data is read by the datasource. This is possible
by adding the following to the metadata:

.. code-block:: yaml

   redact: # formerly named cleanup-guestinfo, which will also work
   - userdata
   - vendordata

When the above snippet is added to the metadata, the datasource will iterate
over the elements in the ``redact`` array and clear each of the keys. For
example, when the guestinfo transport is used, the above snippet will cause
the following commands to be executed:

.. code-block:: shell

   vmware-rpctool "info-set guestinfo.userdata ---"
   vmware-rpctool "info-set guestinfo.userdata.encoding  "
   vmware-rpctool "info-set guestinfo.vendordata ---"
   vmware-rpctool "info-set guestinfo.vendordata.encoding  "

Please note that keys are set to the valid YAML string ``---`` as it is not
possible remove an existing key from the guestinfo key-space. A key's analogous
encoding property will be set to a single white-space character, causing the
datasource to treat the actual key value as plain-text, thereby loading it as
an empty YAML doc (hence the aforementioned ``---``\ ).

Reading the local IP addresses
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This datasource automatically discovers the local IPv4 and IPv6 addresses for
a guest operating system based on the default routes. However, when inspecting
a VM externally, it's not possible to know what the *default* IP address is for
the guest OS. That's why this datasource sets the discovered, local IPv4 and
IPv6 addresses back in the guestinfo namespace as the following keys:


* ``guestinfo.local-ipv4``
* ``guestinfo.local-ipv6``

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

       instance-id: cloud-vm
       local-hostname: cloud-vm
       network:
         version: 2
         ethernets:
           nics:
             match:
               name: ens*
             dhcp4: yes

#. Create the userdata file ``userdata.yaml``\ :

   .. code-block:: yaml

       #cloud-config

       users:
       - default
       - name: akutz
           primary_group: akutz
           sudo: ALL=(ALL) NOPASSWD:ALL
           groups: sudo, wheel
           lock_passwd: true
           ssh_authorized_keys:
           - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDE0c5FczvcGSh/tG4iw+Fhfi/O5/EvUM/96js65tly4++YTXK1d9jcznPS5ruDlbIZ30oveCBd3kT8LLVFwzh6hepYTf0YmCTpF4eDunyqmpCXDvVscQYRXyasEm5olGmVe05RrCJSeSShAeptv4ueIn40kZKOghinGWLDSZG4+FFfgrmcMCpx5YSCtX2gvnEYZJr0czt4rxOZuuP7PkJKgC/mt2PcPjooeX00vAj81jjU2f3XKrjjz2u2+KIt9eba+vOQ6HiC8c2IzRkUAJ5i1atLy8RIbejo23+0P4N2jjk17QySFOVHwPBDTYb0/0M/4ideeU74EN/CgVsvO6JrLsPBR4dojkV5qNbMNxIVv5cUwIy2ThlLgqpNCeFIDLCWNZEFKlEuNeSQ2mPtIO7ETxEL2Cz5y/7AIuildzYMc6wi2bofRC8HmQ7rMXRWdwLKWsR0L7SKjHblIwarxOGqLnUI+k2E71YoP7SZSlxaKi17pqkr0OMCF+kKqvcvHAQuwGqyumTEWOlH6TCx1dSPrW+pVCZSHSJtSTfDW2uzL6y8k10MT06+pVunSrWo5LHAXcS91htHV1M1UrH/tZKSpjYtjMb5+RonfhaFRNzvj7cCE1f3Kp8UVqAdcGBTtReoE8eRUT63qIxjw03a7VwAyB2w+9cu1R9/vAo8SBeRqw== sakutz@gmail.com

#. Please note this step requires that the VM be powered off. All of the
   commands below use the VMware CLI tool, `govc <https://github.com/vmware/govmomi/blob/master/govc>`_.

   Go ahead and assign the path to the VM to the environment variable ``VM``\ :

   .. code-block:: shell

      export VM="/inventory/path/to/the/vm"

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

   .. raw:: html

      <hr />

   .. code-block:: shell

      govc vm.power -off "${VM}"

#.
   Export the environment variables that contain the cloud-init metadata and
   userdata:

   .. code-block:: shell

      export METADATA=$(gzip -c9 <metadata.yaml | { base64 -w0 2>/dev/null || base64; }) \
           USERDATA=$(gzip -c9 <userdata.yaml | { base64 -w0 2>/dev/null || base64; })

#.
   Assign the metadata and userdata to the VM:

   .. code-block:: shell

       govc vm.change -vm "${VM}" \
       -e guestinfo.metadata="${METADATA}" \
       -e guestinfo.metadata.encoding="gzip+base64" \
       -e guestinfo.userdata="${USERDATA}" \
       -e guestinfo.userdata.encoding="gzip+base64"

   Please note the above commands include specifying the encoding for the
   properties. This is important as it informs the datasource how to decode
   the data for cloud-init. Valid values for ``metadata.encoding`` and
   ``userdata.encoding`` include:


   * ``base64``
   * ``gzip+base64``

#.
   Power on the VM:

   .. code-block:: shell

       govc vm.power -vm "${VM}" -on

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
if this value is absent then the instance ID is read from the file
``/sys/class/dmi/id/product_uuid``.

Providing public SSH keys
^^^^^^^^^^^^^^^^^^^^^^^^^

The public SSH keys may be set by way of the metadata key ``public-keys-data``.
Each newline-terminated string will be interpreted as a separate SSH public
key, which will be placed in distro's default user's
``~/.ssh/authorized_keys``. If the value is empty or absent, then nothing will
be written to ``~/.ssh/authorized_keys``.

Configuring the network
^^^^^^^^^^^^^^^^^^^^^^^

The network is configured by setting the metadata key ``network`` with a value
consistent with Network Config Versions
`1 <../network-config-format-v1.html>`_ or
`2 <../network-config-format-v2.html>`_\ , depending on the Linux
distro's version of cloud-init.

The metadata key ``network.encoding`` may be used to indicate the format of
the metadata key "network". Valid encodings are ``base64`` and ``gzip+base64``.
