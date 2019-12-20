.. _datasources:

Datasources
***********

Datasources are sources of configuration data for cloud-init that typically
come from the user (e.g. userdata) or come from the cloud that created the
configuration drive (e.g. metadata). Typical userdata would include files,
yaml, and shell scripts while typical metadata would include server name,
instance id, display name and other cloud specific details.

Since there are multiple ways to provide this data (each cloud solution seems
to prefer its own way) internally a datasource abstract class was created to
allow for a single way to access the different cloud systems methods to provide
this data through the typical usage of subclasses.

Any metadata processed by cloud-init's datasources is persisted as
``/run/cloud-init/instance-data.json``. Cloud-init provides tooling to quickly
introspect some of that data. See :ref:`instance_metadata` for more
information.

Known Sources
=============

The following is a list of documents for each supported datasource:

.. toctree::
   :titlesonly:

   datasources/aliyun.rst
   datasources/altcloud.rst
   datasources/azure.rst
   datasources/cloudsigma.rst
   datasources/cloudstack.rst
   datasources/configdrive.rst
   datasources/digitalocean.rst
   datasources/e24cloud.rst
   datasources/ec2.rst
   datasources/exoscale.rst
   datasources/fallback.rst
   datasources/gce.rst
   datasources/maas.rst
   datasources/nocloud.rst
   datasources/opennebula.rst
   datasources/openstack.rst
   datasources/oracle.rst
   datasources/ovf.rst
   datasources/rbxcloud.rst
   datasources/smartos.rst
   datasources/zstack.rst


Creation
========

The datasource objects have a few touch points with cloud-init.  If you
are interested in adding a new datasource for your cloud platform you will
need to take care of the following items:

* **Identify a mechanism for positive identification of the platform**:
  It is good practice for a cloud platform to positively identify itself
  to the guest.  This allows the guest to make educated decisions based
  on the platform on which it is running. On the x86 and arm64 architectures,
  many clouds identify themselves through DMI data.  For example,
  Oracle's public cloud provides the string 'OracleCloud.com' in the
  DMI chassis-asset field.

  cloud-init enabled images produce a log file with details about the
  platform.  Reading through this log in ``/run/cloud-init/ds-identify.log``
  may provide the information needed to uniquely identify the platform.
  If the log is not present, you can generate it by running from source
  ``./tools/ds-identify`` or the installed location
  ``/usr/lib/cloud-init/ds-identify``.

  The mechanism used to identify the platform will be required for the
  ds-identify and datasource module sections below.

* **Add datasource module ``cloudinit/sources/DataSource<CloudPlatform>.py``**:
  It is suggested that you start by copying one of the simpler datasources
  such as DataSourceHetzner.

* **Add tests for datasource module**:
  Add a new file with some tests for the module to
  ``cloudinit/sources/test_<yourplatform>.py``.  For example see
  ``cloudinit/sources/tests/test_oracle.py``

* **Update ds-identify**:  In systemd systems, ds-identify is used to detect
  which datasource should be enabled or if cloud-init should run at all.
  You'll need to make changes to ``tools/ds-identify``.

* **Add tests for ds-identify**: Add relevant tests in a new class to
  ``tests/unittests/test_ds_identify.py``.  You can use ``TestOracle`` as an
  example.

* **Add your datasource name to the builtin list of datasources:** Add
  your datasource module name to the end of the ``datasource_list``
  entry in ``cloudinit/settings.py``.

* **Add your your cloud platform to apport collection prompts:** Update the
  list of cloud platforms in ``cloudinit/apport.py``.  This list will be
  provided to the user who invokes ``ubuntu-bug cloud-init``.

* **Enable datasource by default in ubuntu packaging branches:**
  Ubuntu packaging branches contain a template file
  ``debian/cloud-init.templates`` that ultimately sets the default
  datasource_list when installed via package.  This file needs updating when
  the commit gets into a package.

* **Add documentation for your datasource**: You should add a new
  file in ``doc/datasources/<cloudplatform>.rst``


API
===

The current interface that a datasource object must provide is the following:

.. sourcecode:: python

    # returns a mime multipart message that contains
    # all the various fully-expanded components that
    # were found from processing the raw user data string
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

    # returns a list of public SSH keys
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
    # when configuring network or hostname related settings, typically
    # assigned either by the cloud provider or the user creating the vm
    def get_hostname(self, fqdn=False)

    def get_package_mirror_info(self)

.. vi: textwidth=79
