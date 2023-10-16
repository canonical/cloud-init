.. _datasource_ovf:

OVF
***

The OVF datasource provides a datasource for reading data from an
`Open Virtualization Format`_ ISO transport.

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
