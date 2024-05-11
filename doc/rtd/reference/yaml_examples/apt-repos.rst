.. _cce-add-apt-repos:

Add primary APT repositories
****************************

This example adds ``apt`` repository configuration to the system.

* For a full list of accepted keys, refer to the `apt configure module docs`_

To add 3rd party repositories, see cloud-config-apt.txt or the
Additional apt configuration and repositories section.


Default: auto select based on cloud metadata in ec2, the default is
<region>.archive.ubuntu.com

#cloud-config
# apt:
#   primary:
#     - arches: [default]
#       uri:
#     use the provided mirror
#       search:
#     search the list for the first mirror.
#     this is currently very limited, only verifying that
#     the mirror is dns resolvable or an IP address
#
# if neither mirror is set (the default)
# then use the mirror provided by the DataSource found.
# In EC2, that means using <region>.ec2.archive.ubuntu.com
#
# if no mirror is provided by the DataSource, but 'search_dns' is
# true, then search for dns names '<distro>-mirror' in each of
# - fqdn of this host per cloud metadata
# - localdomain
# - no domain (which would search domains listed in /etc/resolv.conf)
# If there is a dns entry for <distro>-mirror, then it is assumed that there
# is a distro mirror at http://<distro>-mirror.<domain>/<distro>
#
# That gives the cloud provider the opportunity to set mirrors of a distro
# up and expose them only by creating dns entries.
#
# if none of that is found, then the default distro mirror is used



.. code-block:: yaml

    #cloud-config
    apt:
      primary:
        - arches: [default]
          uri: http://us.archive.ubuntu.com/ubuntu/
    # or
    apt:
      primary:
        - arches: [default]
          search:
            - http://local-mirror.mydomain
            - http://archive.ubuntu.com
    # or
    apt:
      primary:
        - arches: [default]
          search_dns: True

Update APT on first boot
========================

This example will update the ``apt`` repository on first boot; it runs the
``apt-get update`` command.


The default is ``false``. However, if packages are given, or if
``package_upgrade`` is set to ``true``, then the update will be done
irrespective of this setting.

.. code-block:: yaml

    #cloud-config
    package_update: true

.. LINKS
.. _apt configure module docs: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apt-configure
