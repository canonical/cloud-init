.. _datasource_ovf:

OVF
===

The OVF Datasource provides a datasource for reading data from
on an `Open Virtualization Format
<https://en.wikipedia.org/wiki/Open_Virtualization_Format>`_ ISO
transport.

For further information see a full working example in cloud-init's
source code tree in doc/sources/ovf

Configuration
-------------
On VMware platforms, VMTools use is required for OVF datasource configuration
settings as well as vCloud and vSphere admin configuration. User could change
the VMTools configuration options with command::

    vmware-toolbox-cmd config set <section> <key> <value>

The following VMTools configuration options affect cloud-init's behavior on a booted VM:
 * a: [deploypkg] enable-custom-scripts
      If this option is absent in VMTools configuration, the custom script is
      disabled by default for security reasons. Some VMware products could
      change this default behavior (for example: enabled by default) via
      customization specification settings.

VMWare admin can refer to (https://github.com/canonical/cloud-init/blob/master/cloudinit/sources/helpers/vmware/imc/config.py) and set the customization specification settings.

For more information, see [VMware vSphere Product Documentation](https://docs.vmware.com/en/VMware-vSphere/7.0/com.vmware.vsphere.vm_admin.doc/GUID-9A5093A5-C54F-4502-941B-3F9C0F573A39.html) and specific VMTools parameters consumed.

.. vi: textwidth=78
