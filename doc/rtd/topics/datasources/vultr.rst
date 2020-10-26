.. _datasource_vultr:

Vultr
=====
`Vultr <https://www.vultr.com>` platform provides an AWS Ec2 metadata
service clone.  It identifies itself to guests using the dmi
system-manufacturer (/sys/class/dmi/id/sys_vendor) with 'Vultr'.

Vultr also has a native metadata service running at
http://169.254.169.254/v1 for more information, see `Vultr doc`_.

Cloud-init only supports vultr through the EC2 metadata service.

.. _Vultr doc: https://www.vultr.com/metadata/#metadata
.. vi: textwidth=78
