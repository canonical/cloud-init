.. _datasource_zstack:

ZStack
======
ZStack platform provides a AWS Ec2 metadata service, but with different
datasource identity.
More information about ZStack can be found at `ZStack <https://www.zstack.io>`__.

Discovery
---------
To determine whether a vm running on ZStack platform, cloud-init checks DMI
information by 'dmidecode -s chassis-asset-tag', if the output ends with
'.zstack.io', it's running on ZStack platform:


Metadata
^^^^^^^^
Same as EC2, instance metadata can be queried at

::

    GET http://169.254.169.254/2009-04-04/meta-data/
    instance-id
    local-hostname

Userdata
^^^^^^^^
Same as EC2, instance userdata can be queried at

::

    GET http://169.254.169.254/2009-04-04/user-data/
    meta_data.json
    user_data
    password

.. vi: textwidth=78
