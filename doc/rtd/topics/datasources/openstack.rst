.. _datasource_openstack:

OpenStack
=========

This datasource supports reading data from the
`OpenStack Metadata Service
<https://docs.openstack.org/nova/latest/admin/networking-nova.html#metadata-service>`_.

Discovery
-------------
To determine whether a platform looks like it may be OpenStack, cloud-init
checks the following environment attributes as a potential OpenStack platform:

 * Maybe OpenStack if

   * **non-x86 cpu architecture**: because DMI data is buggy on some arches
 * Is OpenStack **if x86 architecture and ANY** of the following

   * **/proc/1/environ**: Nova-lxd contains *product_name=OpenStack Nova*
   * **DMI product_name**: Either *Openstack Nova* or *OpenStack Compute*
   * **DMI chassis_asset_tag** is *OpenTelekomCloud*


Configuration
-------------
The following configuration can be set for the datasource in system
configuration (in `/etc/cloud/cloud.cfg` or `/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

 * **metadata_urls**: This list of urls will be searched for an OpenStack
   metadata service. The first entry that successfully returns a 200 response
   for <url>/openstack will be selected. (default: ['http://169.254.169.254']).
 * **max_wait**:  the maximum amount of clock time in seconds that should be
   spent searching metadata_urls.  A value less than zero will result in only
   one request being made, to the first in the list. (default: -1)
 * **timeout**: the timeout value provided to urlopen for each individual http
   request.  This is used both when selecting a metadata_url and when crawling
   the metadata service. (default: 10)
 * **retries**: The number of retries that should be done for an http request.
   This value is used only after metadata_url is selected. (default: 5)
 * **apply_network_config**: A boolean specifying whether to configure the
   network for the instance based on network_data.json provided by the
   metadata service. When False, only configure dhcp on the primary nic for
   this instances. (default: True)

An example configuration with the default values is provided below:

.. sourcecode:: yaml

  datasource:
   OpenStack:
    metadata_urls: ["http://169.254.169.254"]
    max_wait: -1
    timeout: 10
    retries: 5
    apply_network_config: True


Vendor Data
-----------

The OpenStack metadata server can be configured to serve up vendor data
which is available to all instances for consumption.  OpenStack vendor
data is, generally, a JSON object.

cloud-init will look for configuration in the ``cloud-init`` attribute
of the vendor data JSON object. cloud-init processes this configuration
using the same handlers as user data, so any formats that work for user
data should work for vendor data.

For example, configuring the following as vendor data in OpenStack would
upgrade packages and install ``htop`` on all instances:

.. sourcecode:: json

  {"cloud-init": "#cloud-config\npackage_upgrade: True\npackages:\n - htop"}

For more general information about how cloud-init handles vendor data,
including how it can be disabled by users on instances, see :doc:`/topics/vendordata`.

.. vi: textwidth=78
