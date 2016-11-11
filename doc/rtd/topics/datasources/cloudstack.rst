CloudStack
==========

`Apache CloudStack`_ expose user-data, meta-data, user password and account
sshkey thru the Virtual-Router. For more details on meta-data and user-data,
refer the `CloudStack Administrator Guide`_. 

URLs to access user-data and meta-data from the Virtual Machine. Here 10.1.1.1
is the Virtual Router IP:

.. code:: bash

    http://10.1.1.1/latest/user-data
    http://10.1.1.1/latest/meta-data
    http://10.1.1.1/latest/meta-data/{metadata type}

Configuration
-------------

Apache CloudStack datasource can be configured as follows:

.. code:: yaml

    datasource:
      CloudStack: {}
      None: {}
    datasource_list:
      - CloudStack


.. _Apache CloudStack: http://cloudstack.apache.org/
.. _CloudStack Administrator Guide: http://docs.cloudstack.apache.org/projects/cloudstack-administration/en/latest/virtual_machines.html#user-data-and-meta-data

.. vi: textwidth=78
