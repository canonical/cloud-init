.. _datasource_ovf:

OVF
***

The OVF datasource provides a generic datasource for reading data from an
`Open Virtualization Format`_ ISO transport.

What platforms support OVF
--------------------------

OFV is an open standard which is supported by various virtualization
platforms, including (but not limited to):

GCP
OpenShift
Proxmox
vSphere
VirtualBox
Xen

While these (and many more) platforms support OVF, in some cases cloud-init
has alternative datasources which provide better platform integration.
Make sure to check whether another datasource is exists which is specific to
your platform of choice before trying to use OVF.

Configuration
-------------

Cloud-init gets configurations from an OVF XML file. User-data and network
configuration are provided by properties in the XML which contain key / value
pairs. The user-data is provided by a key named ``user-data``, and network
configuration is provided by a key named ``network-config``.

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

Additional information
----------------------

For further information see a full working example in ``cloud-init``'s
source code tree in :file:`doc/sources/ovf`.

.. _Open Virtualization Format: https://en.wikipedia.org/wiki/Open_Virtualization_Format
