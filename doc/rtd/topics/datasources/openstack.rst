OpenStack
=========

*TODO*

Vendor Data
-----------

The OpenStack metadata server can be configured to serve up vendor data
which is available to all instances for consumption.  OpenStack vendor
data is, generally, a JSON object.

cloud-init will look for configuration in the ``cloud-init`` attribute
of the vendor data JSON object. cloud-init processes this configuration
using the same handlers as user data, so any formats that work for user
data should work for vendor data.

For example, configuring the following as vendor data in OpenStack would
upgrade packages and install ``htop`` on all instances:

.. sourcecode:: json

  {"cloud-init": "#cloud-config\npackage_upgrade: True\npackages:\n - htop"}

For more general information about how cloud-init handles vendor data,
including how it can be disabled by users on instances, see `Vendor Data`_.

.. vi: textwidth=78
