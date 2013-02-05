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
    
    def get_userdata(self, apply_filter=False)
    
    @property
    def launch_index(self)
    
    @property
    def is_disconnected(self)
    
    def get_userdata_raw(self)
    
    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self)
    
    def get_public_ssh_keys(self)
    
    def device_name_to_device(self, name)
    
    def get_locale(self)
    
    @property
    def availability_zone(self)
    
    def get_instance_id(self)
    
    def get_hostname(self, fqdn=False)
    
    def get_package_mirror_info(self)

---------------------------
EC2
---------------------------

TBD

---------------------------
Config Drive
---------------------------

.. include:: ../../sources/configdrive/README.rst

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

TBD

---------------------------
CloudStack
---------------------------

TBD

---------------------------
OVF
---------------------------

See: https://bazaar.launchpad.net/~cloud-init-dev/cloud-init/trunk/files/head:/doc/sources/ovf/

---------------------------
Fallback/None
---------------------------

TBD
