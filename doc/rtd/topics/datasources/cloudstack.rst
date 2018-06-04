.. _datasource_cloudstack:

CloudStack
==========

`Apache CloudStack`_ expose user-data, meta-data, user password and account
sshkey thru the Virtual-Router. The datasource obtains the VR address via
dhcp lease information given to the instance.
For more details on meta-data and user-data,
refer the `CloudStack Administrator Guide`_. 

URLs to access user-data and meta-data from the Virtual Machine. Here 10.1.1.1
is the Virtual Router IP:

.. code:: bash

    http://10.1.1.1/latest/user-data
    http://10.1.1.1/latest/meta-data
    http://10.1.1.1/latest/meta-data/{metadata type}

Configuration
-------------
The following configuration can be set for the datasource in system
configuration (in `/etc/cloud/cloud.cfg` or `/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

 * **max_wait**:  the maximum amount of clock time in seconds that should be
   spent searching metadata_urls.  A value less than zero will result in only
   one request being made, to the first in the list. (default: 120)
 * **timeout**: the timeout value provided to urlopen for each individual http
   request.  This is used both when selecting a metadata_url and when crawling
   the metadata service. (default: 50)

An example configuration with the default values is provided below:

.. sourcecode:: yaml

  datasource:
   CloudStack:
    max_wait: 120
    timeout: 50
    datasource_list:
      - CloudStack


.. _Apache CloudStack: http://cloudstack.apache.org/
.. _CloudStack Administrator Guide: http://docs.cloudstack.apache.org/projects/cloudstack-administration/en/latest/virtual_machines.html#user-data-and-meta-data

.. vi: textwidth=78
