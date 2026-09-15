.. _datasource_qemufwcfg:

QEMU fw_cfg
***********

The ``QemuFwCfg`` datasource reads cloud-init configuration from the QEMU
firmware configuration device (``fw_cfg``). This allows the hypervisor to
inject ``user-data``, ``meta-data``, ``vendor-data``, and ``network-config``
directly into a guest VM without requiring virtual disks, kernel command line
injection, SMBIOS strings, or a network metadata service.

The Linux ``qemu_fw_cfg`` kernel driver (``CONFIG_FW_CFG_SYSFS``) exposes
fw_cfg entries to the guest as sysfs files under
:file:`/sys/firmware/qemu_fw_cfg/by_name/`.
See the `QEMU fw_cfg specification <https://www.qemu.org/docs/master/specs/fw_cfg.html>`_
and the `Linux fw_cfg sysfs driver <https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-firmware-qemu_fw_cfg>`_
for more details.
The datasource reads from the ``opt/io.cloud-init/cloud-init/`` namespace:

- ``opt/io.cloud-init/cloud-init/meta-data``
- ``opt/io.cloud-init/cloud-init/network-config``
- ``opt/io.cloud-init/cloud-init/user-data``
- ``opt/io.cloud-init/cloud-init/vendor-data``

Each entry is exposed in sysfs as a directory; its content is available via
the ``raw`` file inside that directory.

Both ``meta-data`` and ``user-data`` must be present for the datasource to
claim the instance. ``network-config`` and ``vendor-data`` are optional.

Detection
=========

The datasource is detected by ``ds-identify`` during the
:ref:`detect stage<boot-Detect>` when the sysfs directory
:file:`/sys/firmware/qemu_fw_cfg/by_name/opt/io.cloud-init/cloud-init`
exists in the guest.

Injecting configuration
=======================

QEMU command line
-----------------

Use the ``-fw_cfg`` option to inject each slot as a named entry:

.. code-block:: shell-session

   $ qemu-system-x86_64 \
       -fw_cfg name=opt/io.cloud-init/cloud-init/meta-data,file=meta-data \
       -fw_cfg name=opt/io.cloud-init/cloud-init/user-data,file=user-data \
       [other options...]

libvirt domain XML
------------------

When using libvirt, pass the entries via ``<sysinfo type='fwcfg'>`` in the
domain XML:

.. code-block:: xml

   <sysinfo type='fwcfg'>
     <entry name='opt/io.cloud-init/cloud-init/meta-data'>instance-id: vm-001</entry>
     <entry name='opt/io.cloud-init/cloud-init/user-data'>#cloud-config</entry>
   </sysinfo>

Example
=======

The following minimal example creates a VM with a guest user:

**meta-data** (saved as :file:`meta-data`):

.. code-block:: yaml

   instance-id: my-vm-001
   local-hostname: my-vm

**user-data** (saved as :file:`user-data`):

.. code-block:: yaml

   #cloud-config
   users:
     - name: guest
       lock_passwd: false
       shell: /bin/bash
       sudo: ALL=(ALL) NOPASSWD:ALL

   chpasswd:
     users:
       - name: guest
         password: guest
         type: text
     expire: false

Launch the VM:

.. code-block:: shell-session

   $ qemu-system-x86_64 \
       -fw_cfg name=opt/io.cloud-init/cloud-init/meta-data,file=meta-data \
       -fw_cfg name=opt/io.cloud-init/cloud-init/user-data,file=user-data \
       [other options...]

Once the guest has booted, log in as ``guest``.
To debug issues, check the blob contents:

.. code-block:: shell-session

   $ cat /sys/firmware/qemu_fw_cfg/by_name/opt/io.cloud-init/cloud-init/meta-data/raw
   $ cat /sys/firmware/qemu_fw_cfg/by_name/opt/io.cloud-init/cloud-init/user-data/raw

See :ref:`user-data <user_data_formats>` and
:ref:`vendor-data <vendor-data>` for the supported data formats, and
:ref:`network_config_v1` or :ref:`network_config_v2` for network
configuration syntax.
