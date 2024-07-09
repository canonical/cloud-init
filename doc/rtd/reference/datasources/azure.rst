.. _datasource_azure:

Azure
*****

This datasource finds metadata and user data from the Azure cloud platform.

The Azure cloud platform provides initial data to an instance via an attached
CD formatted in UDF. This CD contains a :file:`ovf-env.xml` file that
provides some information. Additional information is obtained via interaction
with the "endpoint".

IMDS
====

Azure provides the `instance metadata service (IMDS)`_, which is a REST service
on ``169.254.169.254`` providing additional configuration information to the
instance. ``Cloud-init`` uses the IMDS for:

- Network configuration for the instance which is applied per boot.
- A pre-provisioning gate which blocks instance configuration until Azure
  fabric is ready to provision.
- Retrieving SSH public keys. ``Cloud-init`` will first try to utilise SSH
  keys returned from IMDS, and if they are not provided from IMDS then it will
  fall back to using the OVF file provided from the CD-ROM. There is a large
  performance benefit to using IMDS for SSH key retrieval, but in order to
  support environments where IMDS is not available then we must continue to
  all for keys from OVF[?]

Configuration
=============

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

* :command:`apply_network_config`

  Boolean set to True to use network configuration described by Azure's IMDS
  endpoint instead of fallback network config of DHCP on eth0. Default is
  True.
* :command:`apply_network_config_for_secondary_ips`

  Boolean to configure secondary IP address(es) for each NIC per IMDS
  configuration. Default is True.
* :command:`data_dir`

  Path used to read metadata files and write crawled data.

* :command:`disk_aliases`

  A dictionary defining which device paths should be interpreted as ephemeral
  images. See :ref:`cc_disk_setup <mod_cc_disk_setup>` module for more info.

Configuration for the datasource can also be read from a ``dscfg`` entry in
the ``LinuxProvisioningConfigurationSet``. Content in ``dscfg`` node is
expected to be base64 encoded YAML content, and it will be merged into the
``'datasource: Azure'`` entry.

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
     Azure:
       apply_network_config: true
       apply_network_config_for_secondary_ips: true
       data_dir: /var/lib/waagent
       disk_aliases:
         ephemeral0: /dev/disk/cloud/azure_resource


User data
=========

User data is provided to ``cloud-init`` inside the :file:`ovf-env.xml` file.
``Cloud-init`` expects that user data will be provided as a base64 encoded
value inside the text child of an element named ``UserData`` or
``CustomData``, which is a direct child of the
``LinuxProvisioningConfigurationSet`` (a sibling to ``UserName``).

If both ``UserData`` and ``CustomData`` are provided, the behaviour is
undefined on which will be selected. In the example below, user data provided
is ``'this is my userdata'``.

Example:

.. code-block:: xml

   <wa:ProvisioningSection>
    <wa:Version>1.0</wa:Version>
    <LinuxProvisioningConfigurationSet
       xmlns="http://schemas.microsoft.com/windowsazure"
       xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
     <ConfigurationSetType>LinuxProvisioningConfiguration</ConfigurationSetType>
     <HostName>myHost</HostName>
     <UserName>myuser</UserName>
     <UserPassword/>
     <CustomData>dGhpcyBpcyBteSB1c2VyZGF0YQ===</CustomData>
     <dscfg>eyJhZ2VudF9jb21tYW5kIjogWyJzdGFydCIsICJ3YWxpbnV4YWdlbnQiXX0=</dscfg>
     <DisableSshPasswordAuthentication>true</DisableSshPasswordAuthentication>
     <SSH>
      <PublicKeys>
       <PublicKey>
        <Fingerprint>6BE7A7C3C8A8F4B123CCA5D0C2F1BE4CA7B63ED7</Fingerprint>
        <Path>this-value-unused</Path>
       </PublicKey>
      </PublicKeys>
     </SSH>
     </LinuxProvisioningConfigurationSet>
   </wa:ProvisioningSection>

HostName
========

When the user launches an instance, they provide a hostname for that instance.
The hostname is provided to the instance in the :file:`ovf-env.xml` file as
``HostName``.

Whatever value the instance provides in its DHCP request will resolve in the
domain returned in the 'search' request.

A generic image will already have a hostname configured. The Ubuntu cloud
images have ``ubuntu`` as the hostname of the system, and the initial DHCP
request on eth0 is not guaranteed to occur after the datasource code has been
run. So, on first boot, that initial value will be sent in the DHCP request
and *that* value will resolve.

In order to make the ``HostName`` provided in the :file:`ovf-env.xml`
resolve, a DHCP request must be made with the new value. ``Cloud-init``
handles this by setting the hostname in the datasource's ``get_data`` method
via :command:`hostname $HostName`, and then bouncing the interface. This
behaviour can be configured or disabled in the datasource config. See
'Configuration' above.

.. _instance metadata service (IMDS): https://docs.microsoft.com/en-us/azure/virtual-machines/windows/instance-metadata-service
