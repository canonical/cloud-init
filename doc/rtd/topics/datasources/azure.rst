.. _datasource_azure:

Azure
=====

This datasource finds metadata and user-data from the Azure cloud platform.


The Azure cloud platform provides initial data to an instance via an attached
CD formatted in UDF.  That CD contains a 'ovf-env.xml' file that provides some
information.  Additional information is obtained via interaction with the
"endpoint".

To find the endpoint, we now leverage the dhcp client's ability to log its
known values on exit.  The endpoint server is special DHCP option 245.
Depending on your networking stack, this can be done
by calling a script in /etc/dhcp/dhclient-exit-hooks or a file in
/etc/NetworkManager/dispatcher.d.  Both of these call a sub-command
'dhclient_hook' of cloud-init itself. This sub-command will write the client
information in json format to /run/cloud-init/dhclient.hook/<interface>.json.

If those files are not available, the fallback is to check the leases file
for the endpoint server (again option 245).

You can define the path to the lease file with the 'dhclient_lease_file'
configuration.


IMDS
----
Azure provides the `instance metadata service (IMDS)
<https://docs.microsoft.com/en-us/azure/virtual-machines/windows/instance-metadata-service>`_
which is a REST service on ``169.254.169.254`` providing additional
configuration information to the instance. Cloud-init uses the IMDS for:

- network configuration for the instance which is applied per boot
- a preprovisioing gate which blocks instance configuration until Azure fabric
  is ready to provision
- retrieving SSH public keys. Cloud-init will first try to utilize SSH keys
  returned from IMDS, and if they are not provided from IMDS then it will
  fallback to using the OVF file provided from the CD-ROM. There is a large
  performance benefit to using IMDS for SSH key retrieval, but in order to
  support environments where IMDS is not available then we must continue to
  all for keys from OVF


Configuration
-------------
The following configuration can be set for the datasource in system
configuration (in ``/etc/cloud/cloud.cfg`` or ``/etc/cloud/cloud.cfg.d/``).

The settings that may be configured are:

 * **apply_network_config**: Boolean set to True to use network configuration
   described by Azure's IMDS endpoint instead of fallback network config of
   dhcp on eth0. Default is True. For Ubuntu 16.04 or earlier, default is
   False.
 * **data_dir**: Path used to read metadata files and write crawled data.
 * **dhclient_lease_file**: The fallback lease file to source when looking for
   custom DHCP option 245 from Azure fabric.
 * **disk_aliases**: A dictionary defining which device paths should be
   interpreted as ephemeral images. See cc_disk_setup module for more info.

Configuration for the datasource can also be read from a
``dscfg`` entry in the ``LinuxProvisioningConfigurationSet``.  Content in
dscfg node is expected to be base64 encoded yaml content, and it will be
merged into the 'datasource: Azure' entry.

An example configuration with the default values is provided below:

.. sourcecode:: yaml

  datasource:
    Azure:
      apply_network_config: true
      data_dir: /var/lib/waagent
      dhclient_lease_file: /var/lib/dhcp/dhclient.eth0.leases
      disk_aliases:
        ephemeral0: /dev/disk/cloud/azure_resource


Userdata
--------
Userdata is provided to cloud-init inside the ovf-env.xml file. Cloud-init
expects that user-data will be provided as base64 encoded value inside the
text child of a element named ``UserData`` or ``CustomData`` which is a direct
child of the ``LinuxProvisioningConfigurationSet`` (a sibling to ``UserName``)
If both ``UserData`` and ``CustomData`` are provided behavior is undefined on
which will be selected.

In the example below, user-data provided is 'this is my userdata'

Example:

.. sourcecode:: xml

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

hostname
--------
When the user launches an instance, they provide a hostname for that instance.
The hostname is provided to the instance in the ovf-env.xml file as
``HostName``.

Whatever value the instance provides in its dhcp request will resolve in the
domain returned in the 'search' request.

A generic image will already have a hostname configured.  The ubuntu
cloud images have 'ubuntu' as the hostname of the system, and the
initial dhcp request on eth0 is not guaranteed to occur after the
datasource code has been run.  So, on first boot, that initial value
will be sent in the dhcp request and *that* value will resolve.

In order to make the ``HostName`` provided in the ovf-env.xml resolve,
a dhcp request must be made with the new value. cloud-init handles
this by setting the hostname in the DataSource's 'get_data' method via
'``hostname $HostName``', and then bouncing the interface.  This
behavior can be configured or disabled in the datasource config.  See
'Configuration' above.

.. vi: textwidth=79
