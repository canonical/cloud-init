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


instance-data
-------------
For reference, cloud-init stores all the metadata, vendordata and userdata
provided by a cloud in a json blob at ``/run/cloud-init/instance-data.json``.
While the json contains datasource-specific keys and names, cloud-init will
maintain a minimal set of standardized keys that will remain stable on any
cloud. Standardized instance-data keys will be present under a "v1" key.
Any datasource metadata cloud-init consumes will all be present under the
"ds" key.

Below is an instance-data.json example from an OpenStack instance:

.. sourcecode:: json

  {
   "base64-encoded-keys": [
    "ds/meta-data/random_seed",
    "ds/user-data"
   ],
   "ds": {
    "ec2_metadata": {
     "ami-id": "ami-0000032f",
     "ami-launch-index": "0",
     "ami-manifest-path": "FIXME",
     "block-device-mapping": {
      "ami": "vda",
      "ephemeral0": "/dev/vdb",
      "root": "/dev/vda"
     },
     "hostname": "xenial-test.novalocal",
     "instance-action": "none",
     "instance-id": "i-0006e030",
     "instance-type": "m1.small",
     "local-hostname": "xenial-test.novalocal",
     "local-ipv4": "10.5.0.6",
     "placement": {
      "availability-zone": "None"
     },
     "public-hostname": "xenial-test.novalocal",
     "public-ipv4": "10.245.162.145",
     "reservation-id": "r-fxm623oa",
     "security-groups": "default"
    },
    "meta-data": {
     "availability_zone": null,
     "devices": [],
     "hostname": "xenial-test.novalocal",
     "instance-id": "3e39d278-0644-4728-9479-678f9212d8f0",
     "launch_index": 0,
     "local-hostname": "xenial-test.novalocal",
     "name": "xenial-test",
     "project_id": "e0eb2d2538814...",
     "random_seed": "A6yPN...",
     "uuid": "3e39d278-0644-4728-9479-678f92..."
    },
    "network_json": {
     "links": [
      {
       "ethernet_mac_address": "fa:16:3e:7d:74:9b",
       "id": "tap9ca524d5-6e",
       "mtu": 8958,
       "type": "ovs",
       "vif_id": "9ca524d5-6e5a-4809-936a-6901..."
      }
     ],
     "networks": [
      {
       "id": "network0",
       "link": "tap9ca524d5-6e",
       "network_id": "c6adfc18-9753-42eb-b3ea-18b57e6b837f",
       "type": "ipv4_dhcp"
      }
     ],
     "services": [
      {
       "address": "10.10.160.2",
       "type": "dns"
      }
     ]
    },
    "user-data": "I2Nsb3VkLWNvbmZpZ...",
    "vendor-data": null
   },
   "v1": {
    "availability-zone": null,
    "cloud-name": "openstack",
    "instance-id": "3e39d278-0644-4728-9479-678f9212d8f0",
    "local-hostname": "xenial-test",
    "region": null
   }
  }



Datasource API
--------------
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
    # created from a single command, thus allowing programmatic
    # filtering on this launch index (or other selective actions)
    @property
    def launch_index(self)

    # the data sources' config_obj is a cloud-config formatted
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

   datasources/aliyun.rst
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
   datasources/gce.rst

.. vi: textwidth=78
