.. _datasources:

Datasources
***********

Datasources are sources of configuration data for ``cloud-init`` that typically
come from the user (i.e., user-data) or come from the cloud that created the
configuration drive (i.e., meta-data). Typical user-data includes files,
YAML, and shell scripts whereas typical meta-data includes server name,
instance id, display name, and other cloud specific details.

Any meta-data processed by ``cloud-init``'s datasources can be inspected. See
:ref:`instance-data` for more information.

How to configure which datasource to use
========================================

In most cases, users of ``cloud-init`` should not have to configure
``cloud-init`` to specify which datasource cloud-init is running on;
``cloud-init`` should be able to identify the platform.

There are exceptions, however, when the :ref:`datasource does not
identify<datasource_ironic>` itself to ``cloud-init``. In this case, the
datasource detection may be overridden by configuring a single datasource
in the :ref:`datasource_list<base_config_datasource_list>`
or by using :ref:`kernel command line arguments<kernel_datasource_override>`.

.. _datasources_supported:

Datasources:
============

The following is a page for each supported datasource:

.. toctree::
   :titlesonly:

   datasources/akamai.rst
   datasources/aliyun.rst
   datasources/altcloud.rst
   datasources/ec2.rst
   datasources/azure.rst
   datasources/cloudcix.rst
   datasources/cloudsigma.rst
   datasources/cloudstack.rst
   datasources/configdrive.rst
   datasources/digitalocean.rst
   datasources/exoscale.rst
   datasources/fallback.rst
   datasources/gce.rst
   datasources/lxd.rst
   datasources/maas.rst
   datasources/nocloud.rst
   datasources/none.rst
   datasources/nwcs.rst
   datasources/opennebula.rst
   datasources/openstack.rst
   datasources/oracle.rst
   datasources/ovf.rst
   datasources/rbxcloud.rst
   datasources/scaleway.rst
   datasources/smartos.rst
   datasources/upcloud.rst
   datasources/vmware.rst
   datasources/vultr.rst
   datasources/wsl.rst
