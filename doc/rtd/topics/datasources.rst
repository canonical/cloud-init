.. _datasources:

=========
Datasources
=========
----------
 What is a datasource?
----------

Datasources are sources of configuration data for cloud-init that typically come
from the user (aka userdata) or come from the stack that created the configuration
drive (aka metadata). Typical userdata would include files, yaml, and shell scripts
while typical metadata would include server name, instance id, display name and other
cloud specific details. Since there are multiple ways to provide this data (each cloud
solution seems to prefer its own way) internally a datasource abstract class was
created to allow for a single way to access the different cloud systems methods 
to provide this data through the typical usage of subclasses.

The current interface that a datasource object must provide is the following:

.. sourcecode:: python
    
    # returns a mime multipart message that contains
    # all the various fully-expanded components that
    # were found from processing the raw userdata string
    # - when filtering only the mime messages targeting
    #   this instance id will be returned (or messages with
    #   no instance id)
    def get_userdata(self, apply_filter=False)
    
    # returns the raw userdata string (or none)
    def get_userdata_raw(self)
    
    # returns a integer (or none) which can be used to identify
    # this instance in a group of instances which are typically
    # created from a single command, thus allowing programatic
    # filtering on this launch index (or other selective actions)
    @property
    def launch_index(self)
    
    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self)
    
    #returns a list of public ssh keys
    def get_public_ssh_keys(self)
    
    # translates a device 'short' name into the actual physical device
    # fully qualified name (or none if said physical device is not attached
    # or does not exist)
    def device_name_to_device(self, name)
    
    # gets the locale string this instance should be applying 
    # which typically used to adjust the instances locale settings files
    def get_locale(self)
    
    @property
    def availability_zone(self)
    
    # gets the instance id that was assigned to this instance by the 
    # cloud provider or when said instance id does not exist in the backing
    # metadata this will return 'iid-datasource'
    def get_instance_id(self)
    
    # gets the fully qualified domain name that this host should  be using
    # when configuring network or hostname releated settings, typically
    # assigned either by the cloud provider or the user creating the vm
    def get_hostname(self, fqdn=False)
    
    def get_package_mirror_info(self)

---------------------------
EC2
---------------------------

The EC2 datasource is the oldest and most widely used datasource that cloud-init
supports. This datasource interacts with a *magic* ip that is provided to the 
instance by the cloud provider. Typically this ip is ``169.254.169.254`` of which
at this ip a http server is provided to the instance so that the instance can make
calls to get instance userdata and instance metadata.

Metadata is accessible via the following URL:

::
    
    GET http://169.254.169.254/2009-04-04/meta-data/
    ami-id
    ami-launch-index
    ami-manifest-path
    block-device-mapping/
    hostname
    instance-id
    instance-type
    local-hostname
    local-ipv4
    placement/
    public-hostname
    public-ipv4
    public-keys/
    reservation-id
    security-groups

Userdata is accessible via the following URL:

::
    
    GET http://169.254.169.254/2009-04-04/user-data
    1234,fred,reboot,true | 4512,jimbo, | 173,,,

Note that there are multiple versions of this data provided, cloud-init
by default uses **2009-04-04** but newer versions can be supported with
relative ease (newer versions have more data exposed, while maintaining
backward compatibility with the previous versions). 

To see which versions are supported from your cloud provider use the following URL:

::
    
    GET http://169.254.169.254/
    1.0
    2007-01-19
    2007-03-01
    2007-08-29
    2007-10-10
    2007-12-15
    2008-02-01
    2008-09-01
    2009-04-04
    ...
    latest
        
---------------------------
Config Drive
---------------------------

.. include:: ../../sources/configdrive/README.rst

---------------------------
OpenNebula
---------------------------

.. include:: ../../sources/opennebula/README.rst

---------------------------
Alt cloud
---------------------------

.. include:: ../../sources/altcloud/README.rst

---------------------------
No cloud
---------------------------

.. include:: ../../sources/nocloud/README.rst

---------------------------
MAAS
---------------------------

*TODO*

For now see: http://maas.ubuntu.com/

---------------------------
CloudStack
---------------------------

*TODO*

---------------------------
OVF
---------------------------

*TODO*

For now see: https://bazaar.launchpad.net/~cloud-init-dev/cloud-init/trunk/files/head:/doc/sources/ovf/

---------------------------
Fallback/None
---------------------------

This is the fallback datasource when no other datasource can be selected. It is
the equivalent of a *empty* datasource in that it provides a empty string as userdata
and a empty dictionary as metadata. It is useful for testing as well as for when
you do not have a need to have an actual datasource to meet your instance 
requirements (ie you just want to run modules that are not concerned with any
external data). It is typically put at the end of the datasource search list
so that if all other datasources are not matched, then this one will be so that
the user is not left with an inaccessible instance.

**Note:** the instance id that this datasource provides is ``iid-datasource-none``.

.. _boto: http://docs.pythonboto.org/en/latest/
