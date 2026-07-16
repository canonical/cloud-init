.. _datasource_vmware:

VMware
******

This datasource is for use with systems running on a VMware platform such as
vSphere and currently supports the following data transports:

* `Guest OS Customization`_
* `GuestInfo keys`_

The configuration method is dependent upon the transport.

Guest OS customization
======================

The following configuration can be set for this datasource in ``cloud-init``
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

System configuration
--------------------

* ``disable_vmware_customization``: true (disable) or false (enable) the VMware
  traditional Linux guest customization. Traditional Linux guest customization
  is customizing a Linux virtual machine with a
  `traditional Linux customization specification`_. Setting this configuration
  to false is required to make sure this datasource is found in ``ds-identify``
  when using Guest OS customization transport. VMware Tools only checks this
  configuration in :file:`/etc/cloud/cloud.cfg`.

  Default: true

Datasource configuration
------------------------

* ``allow_raw_data``: true (enable) or false (disable) the VMware customization
  using ``cloud-init`` meta-data and user-data directly. Since vSphere 7.0
  Update 3 version, users can create a Linux customization specification with
  minimal ``cloud-init`` meta-data and user-data, and apply this specification
  to a virtual machine. This datasource will parse the meta-data and user-data
  and configure the virtual machine with them. See
  `Guest customization using cloud-init`_ for more information.

  Default: true

* ``vmware_cust_file_max_wait``: The maximum amount of clock time (in seconds)
  that should be spent waiting for VMware customization files.

  Default: 15

Configuration examples
----------------------

1. Enable VMware customization and set the maximum waiting time for the
   VMware customization file to 10 seconds:

   Set ``disable_vmware_customization`` in the :file:`/etc/cloud/cloud.cfg`

   .. code-block:: yaml

      disable_vmware_customization: false

   Create a :file:`/etc/cloud/cloud.cfg.d/99-vmware-guest-customization.cfg`
   with the following content

   .. code-block:: yaml

      datasource:
        VMware:
          vmware_cust_file_max_wait: 10

2. Enable VMware customization but only try to apply a traditional Linux
   Guest Customization configuration, and set the maximum waiting time for
   the VMware customization file to 10 seconds:

   Set ``disable_vmware_customization`` in the :file:`/etc/cloud/cloud.cfg`

   .. code-block:: yaml

      disable_vmware_customization: false

   Create a :file:`/etc/cloud/cloud.cfg.d/99-vmware-guest-customization.cfg`
   with the following content

   .. code-block:: yaml

      datasource:
        VMware:
          allow_raw_data: false
          vmware_cust_file_max_wait: 10

VMware Tools configuration
--------------------------

`VMware Tools`_ is required for this datasource's configuration settings, as
well as vCloud and vSphere admin configuration. Users can change the VMware
Tools configuration options with the following command:

.. code-block:: shell

    vmware-toolbox-cmd config set <section> <key> <value>

The following VMware Tools configuration option affects this datasource's
behaviour when applying customization configuration with custom scripts:

* ``[deploypkg] enable-custom-scripts``: If this option is absent in VMware
  Tools configuration, the custom script is disabled by default for security
  reasons. Some VMware products could change this default behaviour (for
  example: enabled by default) via customization of the specification settings.

  VMware admins can refer to `customization configuration`_ and set the
  customization specification settings.

For more information, see `VMware vSphere Product Documentation`_ and specific
VMware Tools configuration options.

GuestInfo keys
==============

One method of providing meta-data, user-data, and vendor-data is by setting the
following key/value pairs on a VM's ``extraConfig`` `property`_:

.. list-table::
   :header-rows: 1

   * - Property
     - Description
   * - ``guestinfo.metadata``
     - A YAML or JSON document containing the ``cloud-init`` meta-data.
   * - ``guestinfo.metadata.encoding``
     - The encoding type for ``guestinfo.metadata``.
   * - ``guestinfo.userdata``
     - A YAML document containing the ``cloud-init`` user-data.
   * - ``guestinfo.userdata.encoding``
     - The encoding type for ``guestinfo.userdata``.
   * - ``guestinfo.vendordata``
     - A YAML document containing the ``cloud-init`` vendor-data.
   * - ``guestinfo.vendordata.encoding``
     - The encoding type for ``guestinfo.vendordata``.


All ``guestinfo.*.encoding`` values may be set to ``base64`` or
``gzip+base64``.

Features
========

This section reviews several features available in this datasource.

Graceful rpctool fallback
-------------------------

The datasource initially attempts to use the program ``vmware-rpctool`` if it
is available. However, if the program returns a non-zero exit code, then the
datasource falls back to using the program ``vmtoolsd`` with the ``--cmd``
argument.

On some older versions of ESXi and open-vm-tools, the ``vmware-rpctool``
program is much more performant than ``vmtoolsd``. While this gap was
closed, it is not reasonable to expect the guest where cloud-init is running to
know whether the underlying hypervisor has the patch.

Additionally, vSphere VMs may have the following present in their VMX file:

.. code-block:: ini

   guest_rpc.rpci.auth.cmd.info-set = "TRUE"
   guest_rpc.rpci.auth.cmd.info-get = "TRUE"

The above configuration causes the ``vmware-rpctool`` command to return a
non-zero exit code with the error message ``Permission denied``. If this should
occur, the datasource falls back to using ``vmtoolsd``.

Example instance-data
---------------------

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


Redacting sensitive information (GuestInfo keys transport only)
---------------------------------------------------------------

Sometimes the ``cloud-init`` user-data might contain sensitive information,
and it may be desirable to have the ``guestinfo.userdata`` key (or other
``guestinfo`` keys) redacted as soon as its data is read by the datasource.
This is possible by adding the following to the meta-data:

.. code-block:: yaml

   redact: # formerly named cleanup-guestinfo, which will also work
   - userdata
   - vendordata

When the above snippet is added to the meta-data, the datasource will iterate
over the elements in the ``redact`` array and clear each of the keys. For
example, when the ``guestinfo`` transport is used, the above snippet will cause
the following commands to be executed:

.. code-block:: shell

   vmware-rpctool "info-set guestinfo.userdata ---"
   vmware-rpctool "info-set guestinfo.userdata.encoding  "
   vmware-rpctool "info-set guestinfo.vendordata ---"
   vmware-rpctool "info-set guestinfo.vendordata.encoding  "

Please note that keys are set to the valid YAML string ``---`` as it is not
possible remove an existing key from the ``guestinfo`` key-space. A key's
analogous encoding property will be set to a single white-space character,
causing the datasource to treat the actual key value as plain-text, thereby
loading it as an empty YAML doc (hence the aforementioned ``---``\ ).

Reading the local IP addresses
------------------------------

This datasource automatically discovers the local IPv4 and IPv6 addresses for
a guest operating system based on the default routes. However, when inspecting
a VM externally, it's not possible to know what the *default* IP address is for
the guest OS. That's why this datasource sets the discovered, local IPv4 and
IPv6 addresses back in the ``guestinfo`` namespace as the following keys:

* ``guestinfo.local-ipv4``
* ``guestinfo.local-ipv6``

It is possible that a host may not have any default, local IP addresses. It's
also possible the reported, local addresses are link-local addresses. But these
two keys may be used to discover what this datasource determined were the local
IPv4 and IPv6 addresses for a host.

Waiting on the network
----------------------

It is possible to instruct the datasource to wait until an IPv4 or IPv6 address
is available before processing instance-data with the following meta-data
properties:

.. code-block:: yaml

   wait-on-network:
     ipv4: true
     ipv6: true

If either of the above values are true, then the datasource will sleep for a
second, check the network status, and repeat until one or both addresses from
the specified families are available.

Update Event support
--------------------

The VMware datasource supports the following types of update events:

* Network -- ``boot``, ``boot-new-instance``, and ``hotplug``

This means the guest will reconfigure networking from the network
configuration provided via guestinfo, IMC, etc. each time the guest
boots or even when a new network interface is added.

It is possible to override the data source's default set of configured
update events by specifying which events to use via user data.
For example, the following snippet from user data would disable the
`hotplug` event:

   .. code-block:: yaml

       #cloud-config
       updates:
         network:
           when: ["boot", "boot-new-instance"]

Determining the supported and enabled update events
---------------------------------------------------

This datasource also advertises the scope and type of the supported
and enabled events.

The ``guestinfo`` key ``guestinfo.cloudinit.updates.supported``
contains a list of the supported scopes and types that adheres to the
format ``SCOPE=TYPE[;TYPE][,SCOPE=TYPE[;TYPE]]``, for example:

* ``network=boot;hotplug``
* ``network=boot-new-instance``

The value is based on the events supported by the datasource, whether
or not the event is enabled. To inspect which events are enabled, use
``guestinfo.cloudinit.updates.enabled``.

This allows a consumer to determine if different versions of the
datasource have different supported event types, regardless of which
events are enabled.

Network drivers and the hotplug update event
--------------------------------------------

By default, this datasource only responds to hotplug events if the
driver is one of the following:

* ``e1000``
* ``e1000e``
* ``vlance``
* ``vmxnet2``
* ``vmxnet3``
* ``vrdma``

This prevents responding unintentionally to interfaces created by
Docker or other programs. However, it is also possible to override this
list by setting ``metadata.network-drivers`` to a list of drivers:

   .. code-block:: yaml

       network-drivers:
       - vmxnet2
       - vmxnet3

The above snippet means only NICs that use either the ``vmxnet2`` or
``vmxnet3`` drivers will respond to hotplug events.

Walkthrough of GuestInfo keys transport
=======================================

The following series of steps is a demonstration of how to configure a VM with
this datasource using the GuestInfo keys transport:

#. Create the meta-data file for the VM. Save the following YAML to a file named
   :file:`meta-data.yaml`\:

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

#. Create the user-data file :file:`user-data.yaml`\:

   .. code-block:: yaml

       #cloud-config

       users:
       - default
       - name: akutz
         primary_group: akutz
         sudo: "ALL=(ALL) NOPASSWD:ALL"
         groups: sudo, wheel
         lock_passwd: true
         ssh_authorized_keys:
         - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDE0c5FczvcGSh/tG4iw+Fhfi/O5/EvUM/96js65tly4++YTXK1d9jcznPS5ruDlbIZ30oveCBd3kT8LLVFwzh6hepYTf0YmCTpF4eDunyqmpCXDvVscQYRXyasEm5olGmVe05RrCJSeSShAeptv4ueIn40kZKOghinGWLDSZG4+FFfgrmcMCpx5YSCtX2gvnEYZJr0czt4rxOZuuP7PkJKgC/mt2PcPjooeX00vAj81jjU2f3XKrjjz2u2+KIt9eba+vOQ6HiC8c2IzRkUAJ5i1atLy8RIbejo23+0P4N2jjk17QySFOVHwPBDTYb0/0M/4ideeU74EN/CgVsvO6JrLsPBR4dojkV5qNbMNxIVv5cUwIy2ThlLgqpNCeFIDLCWNZEFKlEuNeSQ2mPtIO7ETxEL2Cz5y/7AIuildzYMc6wi2bofRC8HmQ7rMXRWdwLKWsR0L7SKjHblIwarxOGqLnUI+k2E71YoP7SZSlxaKi17pqkr0OMCF+kKqvcvHAQuwGqyumTEWOlH6TCx1dSPrW+pVCZSHSJtSTfDW2uzL6y8k10MT06+pVunSrWo5LHAXcS91htHV1M1UrH/tZKSpjYtjMb5+RonfhaFRNzvj7cCE1f3Kp8UVqAdcGBTtReoE8eRUT63qIxjw03a7VwAyB2w+9cu1R9/vAo8SBeRqw== sakutz@gmail.com

#. Please note this step requires that the VM be powered off. All of the
   commands below use the VMware CLI tool, `govc`_.

   Go ahead and assign the path to the VM to the environment variable ``VM``\:

   .. code-block:: shell

      export VM="/inventory/path/to/the/vm"

#. Power off the VM:

   .. raw:: html

      <hr />

      &#x26a0;&#xfe0f; <strong>First Boot Mode</strong>

   To ensure the next power-on operation results in a first-boot scenario for
   ``cloud-init``, it may be necessary to run the following command just before
   powering off the VM:

   .. code-block:: bash

      cloud-init clean --logs --machine-id

   Otherwise ``cloud-init`` may not run in first-boot mode. For more
   information on how the boot mode is determined, please see the
   :ref:`first boot documentation <First_boot_determination>`.

   .. raw:: html

      <hr />

   .. code-block:: shell

      govc vm.power -off "${VM}"

#. Export the environment variables that contain the ``cloud-init`` meta-data
   and user-data:

   .. code-block:: shell

      export METADATA=$(gzip -c9 <meta-data.yaml | { base64 -w0 2>/dev/null || base64; }) \
           USERDATA=$(gzip -c9 <user-data.yaml | { base64 -w0 2>/dev/null || base64; })

#. Assign the meta-data and user-data to the VM:

   .. code-block:: shell

       govc vm.change -vm "${VM}" \
       -e guestinfo.metadata="${METADATA}" \
       -e guestinfo.metadata.encoding="gzip+base64" \
       -e guestinfo.userdata="${USERDATA}" \
       -e guestinfo.userdata.encoding="gzip+base64"

   .. note::
      Please note the above commands include specifying the encoding for the
      properties. This is important as it informs the datasource how to decode
      the data for ``cloud-init``. Valid values for ``metadata.encoding`` and
      ``userdata.encoding`` include:

      * ``base64``
      * ``gzip+base64``

#. Power on the VM:

   .. code-block:: shell

       govc vm.power -on "${VM}"

If all went according to plan, the CentOS box is:

* Locked down, allowing SSH access only for the user in the user-data.
* Configured for a dynamic IP address via DHCP.
* Has a hostname of ``cloud-vm``.

Examples of common configurations
=================================

Setting the hostname
--------------------

The hostname is set by way of the meta-data key ``local-hostname``.

Setting the instance ID
-----------------------

The instance ID may be set by way of the meta-data key ``instance-id``.
However, if this value is absent then the instance ID is read from the file
:file:`/sys/class/dmi/id/product_uuid`.

Providing public SSH keys
-------------------------

The public SSH keys may be set by way of the meta-data key
``public-keys-data``. Each newline-terminated string will be interpreted as a
separate SSH public key, which will be placed in distro's default user's
:file:`~/.ssh/authorized_keys`. If the value is empty or absent, then nothing
will be written to :file:`~/.ssh/authorized_keys`.

Configuring the network
-----------------------

The network is configured by setting the meta-data key ``network`` with a value
consistent with Network Config :ref:`Version 1 <network_config_v1>` or
:ref:`Version 2 <network_config_v2>`, depending on the Linux distro's version
of ``cloud-init``.

The meta-data key ``network.encoding`` may be used to indicate the format of
the meta-data key ``network``. Valid encodings are ``base64`` and
``gzip+base64``.


.. LINKS
.. _Guest OS Customization: https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-vm-administration/
.. _GuestInfo keys: https://github.com/vmware/govmomi/blob/master/govc/USAGE.md
.. _traditional Linux customization specification: https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-vm-administration/GUID-EB5F090E-723C-4470-B640-50B35D1EC016.html#GUID-9A5093A5-C54F-4502-941B-3F9C0F573A39__GUID-40C60643-A2EB-4B05-8927-B51AF7A6CC5E
.. _Guest customization using cloud-init: https://developer.vmware.com/docs/17686/vsphere-web-services-sdk-programming-guide--8-0-/GUID-75E27FA9-2E40-4CBF-BF3D-22DCFC8F11F7.html
.. _VMware Tools: https://docs.vmware.com/en/VMware-Tools/index.html
.. _customization configuration: https://github.com/canonical/cloud-init/blob/main/cloudinit/sources/helpers/vmware/imc/config.py
.. _VMware vSphere Product Documentation: https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-vm-administration/GUID-EB5F090E-723C-4470-B640-50B35D1EC016.html#GUID-9A5093A5-C54F-4502-941B-3F9C0F573A39__GUID-40C60643-A2EB-4B05-8927-B51AF7A6CC5E
.. _property: https://docs.vmware.com/en/VMware-vSphere/index.html
.. _govc: https://github.com/vmware/govmomi/blob/master/govc
