.. _datasources:

***********
Datasources
***********

What is a datasource?
=====================

Datasources are sources of configuration data for cloud-init that typically
come from the user (aka userdata) or come from the stack that created the
configuration drive (aka metadata). Typical userdata would include files,
yaml, and shell scripts while typical metadata would include server name,
instance id, display name and other cloud specific details. Since there are
multiple ways to provide this data (each cloud solution seems to prefer its
own way) internally a datasource abstract class was created to allow for a
single way to access the different cloud systems methods to provide this data
through the typical usage of subclasses.

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


Datasource Documentation
========================
The following is a list of the implemented datasources.
Follow for more information.

.. toctree::
   :maxdepth: 2

   datasources/altcloud.rst
   datasources/azure.rst
   datasources/cloudsigma.rst
   datasources/cloudstack.rst
   datasources/configdrive.rst
   datasources/digitalocean.rst
   datasources/ec2.rst
   datasources/maas.rst
   datasources/nocloud.rst
   datasources/opennebula.rst
   datasources/openstack.rst
   datasources/ovf.rst
   datasources/smartos.rst
   datasources/fallback.rst

.. vi: textwidth=78
