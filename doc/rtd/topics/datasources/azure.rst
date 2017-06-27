.. _datasource_azure:

Azure
=====

This datasource finds metadata and user-data from the Azure cloud platform.

Azure Platform
--------------
The azure cloud-platform provides initial data to an instance via an attached
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

In order for cloud-init to leverage this method to find the endpoint, the
cloud.cfg file must contain:

datasource:
  Azure:
    set_hostname: False
    agent_command: __builtin__

If those files are not available, the fallback is to check the leases file
for the endpoint server (again option 245).

You can define the path to the lease file with the 'dhclient_lease_file'
configuration.  The default value is /var/lib/dhcp/dhclient.eth0.leases.

    dhclient_lease_file: /var/lib/dhcp/dhclient.eth0.leases

walinuxagent
------------
In order to operate correctly, cloud-init needs walinuxagent to provide much
of the interaction with azure.  In addition to "provisioning" code, walinux
does the following on the agent is a long running daemon that handles the
following things:
- generate a x509 certificate and send that to the endpoint

waagent.conf config
^^^^^^^^^^^^^^^^^^^
in order to use waagent.conf with cloud-init, the following settings are recommended.  Other values can be changed or set to the defaults.

  ::

   # disabling provisioning turns off all 'Provisioning.*' function
   Provisioning.Enabled=n
   # this is currently not handled by cloud-init, so let walinuxagent do it.
   ResourceDisk.Format=y
   ResourceDisk.MountPoint=/mnt


Userdata
--------
Userdata is provided to cloud-init inside the ovf-env.xml file. Cloud-init
expects that user-data will be provided as base64 encoded value inside the
text child of a element named ``UserData`` or ``CustomData`` which is a direct
child of the ``LinuxProvisioningConfigurationSet`` (a sibling to ``UserName``)
If both ``UserData`` and ``CustomData`` are provided behavior is undefined on
which will be selected.

In the example below, user-data provided is 'this is my userdata', and the
datasource config provided is ``{"agent_command": ["start", "walinuxagent"]}``.
That agent command will take affect as if it were specified in system config.

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

Configuration
-------------
Configuration for the datasource can be read from the system config's or set
via the `dscfg` entry in the `LinuxProvisioningConfigurationSet`.  Content in
dscfg node is expected to be base64 encoded yaml content, and it will be
merged into the 'datasource: Azure' entry.

The '``hostname_bounce: command``' entry can be either the literal string
'builtin' or a command to execute.  The command will be invoked after the
hostname is set, and will have the 'interface' in its environment.  If
``set_hostname`` is not true, then ``hostname_bounce`` will be ignored.

An example might be:
  command:  ["sh", "-c", "killall dhclient; dhclient $interface"]

.. code:: yaml

  datasource:
   agent_command
   Azure:
    agent_command: [service, walinuxagent, start]
    set_hostname: True
    hostname_bounce:
     # the name of the interface to bounce
     interface: eth0
     # policy can be 'on', 'off' or 'force'
     policy: on
     # the method 'bounce' command.
     command: "builtin"
     hostname_command: "hostname"

hostname
--------
When the user launches an instance, they provide a hostname for that instance.
The hostname is provided to the instance in the ovf-env.xml file as
``HostName``.

Whatever value the instance provides in its dhcp request will resolve in the
domain returned in the 'search' request.

The interesting issue is that a generic image will already have a hostname
configured.  The ubuntu cloud images have 'ubuntu' as the hostname of the
system, and the initial dhcp request on eth0 is not guaranteed to occur after
the datasource code has been run.  So, on first boot, that initial value will
be sent in the dhcp request and *that* value will resolve.

In order to make the ``HostName`` provided in the ovf-env.xml resolve, a
dhcp request must be made with the new value.  Walinuxagent (in its current
version) handles this by polling the state of hostname and bouncing ('``ifdown
eth0; ifup eth0``' the network interface if it sees that a change has been
made.

cloud-init handles this by setting the hostname in the DataSource's 'get_data'
method via '``hostname $HostName``', and then bouncing the interface.  This
behavior can be configured or disabled in the datasource config.  See
'Configuration' above.

.. vi: textwidth=78
