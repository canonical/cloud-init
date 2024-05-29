.. _datasource_openstack:

OpenStack
*********

This datasource supports reading data from the `OpenStack Metadata Service`_.

Discovery
=========

To determine whether a platform looks like it may be OpenStack, ``cloud-init``
checks the following environment attributes as a potential OpenStack platform:

* May be OpenStack **if**:

  * ``non-x86 cpu architecture``: because DMI data is buggy on some arches.

* Is OpenStack **if** x86 architecture and **ANY** of the following:

  * ``/proc/1/environ``: ``Nova-lxd`` contains
    ``product_name=OpenStack Nova``.
  * ``DMI product_name``: Either ``Openstack Nova`` or ``OpenStack Compute``.
  * ``DMI chassis_asset_tag`` is ``HUAWEICLOUD``, ``OpenTelekomCloud``,
    ``SAP CCloud VM``, ``OpenStack Nova`` (since 19.2) or
    ``OpenStack Compute`` (since 19.2).

Configuration
=============

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are as follows:

``metadata_urls``
-----------------

This list of URLs will be searched for an OpenStack metadata service. The
first entry that successfully returns a 200 response for ``<url>/openstack``
will be selected.

Default: ['http://169.254.169.254'])

``max_wait``
------------

The maximum amount of clock time (in seconds) that should be spent searching
``metadata_urls``. A value less than zero will result in only one request
being made, to the first in the list.

Default: -1

``timeout``
-----------

The timeout value provided to ``urlopen`` for each individual http request.
This is used both when selecting a ``metadata_url`` and when crawling the
metadata service.

Default: 10

``retries``
-----------

The number of retries that should be attempted for an http request. This
value is used only after ``metadata_url`` is selected.

Default: 5

``apply_network_config``
------------------------

A boolean specifying whether to configure the network for the instance based
on :file:`network_data.json` provided by the metadata service. When False,
only configure DHCP on the primary NIC for this instance.

Default: True

Example configuration
=====================

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
     OpenStack:
       metadata_urls: ["http://169.254.169.254"]
       max_wait: -1
       timeout: 10
       retries: 5
       apply_network_config: True


Vendor Data
===========

The OpenStack metadata server can be configured to serve up vendor data,
which is available to all instances for consumption. OpenStack vendor data is
generally a JSON object.

``Cloud-init`` will look for configuration in the ``cloud-init`` attribute
of the vendor data JSON object. ``Cloud-init`` processes this configuration
using the same handlers as user data, so any formats that work for user
data should work for vendor data.

For example, configuring the following as vendor data in OpenStack would
upgrade packages and install ``htop`` on all instances:

.. code-block:: json

   {"cloud-init": "#cloud-config\npackage_upgrade: True\npackages:\n - htop"}

For more general information about how ``cloud-init`` handles vendor data,
including how it can be disabled by users on instances, see our
:ref:`explanation topic<vendordata>`.

OpenStack can also be configured to provide "dynamic vendordata"
which is provided by the DynamicJSON provider and appears under a
different metadata path, :file:`/vendor_data2.json`.

``Cloud-init`` will look for a ``cloud-init`` at the :file:`vendor_data2`
path; if found, settings are applied after (and, hence, overriding) the
settings from static vendor data. Both sets of vendor data can be overridden
by user data.

.. _datasource_ironic:

OpenStack Ironic Bare Metal
===========================

During boot, cloud-init typically has to identify which platform it is running
on. Since OpenStack Ironic Bare Metal doesn't provide a method for cloud-init
to discover that it is running on Ironic, extra user configuration is required.

Cloud-init provides two methods to do this:

Method 1: Configuration file
----------------------------

Explicitly set ``datasource_list`` to only ``openstack``, such as:

.. code-block:: yaml

   datasource_list: ["openstack"]

Method 2: Kernel command line
-----------------------------

Set the kernel command line to configure
:ref:`datasource override <kernel_datasource_override>`.

Example using Ubuntu + GRUB2:

.. code-block::

    $ echo 'ds=openstack' >> /etc/default/grub
    $ grub-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg


.. _OpenStack Metadata Service: https://docs.openstack.org/nova/latest/admin/metadata-service.html
