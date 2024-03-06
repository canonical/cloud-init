.. _datasource_zstack:

ZStack
******

ZStack platform provides an AWS EC2 metadata service, but with different
datasource identity. More information about ZStack can be found at
`ZStack`_.

Discovery
=========

To determine whether a VM is running on the ZStack platform, ``cloud-init``
checks DMI information via ``dmidecode -s chassis-asset-tag``. If the output
ends with ``.zstack.io``, it's running on the ZStack platform.

Metadata
--------

The same way as with EC2, instance metadata can be queried at: ::

    GET http://169.254.169.254/2009-04-04/meta-data/
    instance-id
    local-hostname

User data
---------

The same way as with EC2, instance user data can be queried at: ::

    GET http://169.254.169.254/2009-04-04/user-data/
    meta_data.json
    user_data
    password

.. _ZStack: https://www.zstack.io
