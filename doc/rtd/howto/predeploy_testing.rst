.. _predeploy_testing:

How to test ``cloud-init`` locally before deploying
***************************************************

It's very likely that you will want to test ``cloud-init`` locally before
deploying it to the cloud. Fortunately, there are several different virtual
machines (VMs) and container tools that are ideal for this sort of local
testing.

In this guide, we will show how to use three of the most popular tools:
`Multipass`_, `LXD`_ and `QEMU`_.

Multipass
=========

Multipass is a cross-platform tool for launching Ubuntu VMs across Linux,
Windows, and macOS.

When a user launches a Multipass VM, user data can be passed by adding the
``--cloud-init`` flag and the appropriate YAML file containing the user data:

.. code-block:: shell-session

    $ multipass launch bionic --name test-vm --cloud-init userdata.yaml

Multipass will validate the YAML syntax of the cloud-config file before
attempting to start the VM! A nice addition which saves time when you're
experimenting and launching instances with various cloud-configs.

Multipass *only* supports passing user data, and *only* as YAML cloud-config
files. Passing a script, a MIME archive, or any of the other user data formats
``cloud-init`` supports will result in an error from the YAML syntax validator.

LXD
===

LXD offers a streamlined user experience for using Linux system containers.
With LXD, a user can pass:

* user data,
* vendor data,
* metadata, and
* network configuration.

The following command initialises a container with user data:

.. code-block:: shell-session

    $ lxc init ubuntu-daily:bionic test-container
    $ lxc config set test-container user.user-data - < userdata.yaml
    $ lxc start test-container

To avoid the extra commands this can also be done at launch:

.. code-block:: shell-session

    $ lxc launch ubuntu-daily:bionic test-container --config=user.user-data="$(cat userdata.yaml)"

Finally, a profile can be set up with the specific data if you need to
launch this multiple times:

.. code-block:: shell-session

    $ lxc profile create dev-user-data
    $ lxc profile set dev-user-data user.user-data - < cloud-init-config.yaml
    $ lxc launch ubuntu-daily:bionic test-container -p default -p dev-user-data

The above examples all show how to pass user data. To pass other types of
configuration data use the config option specified below:

+----------------+---------------------------+
| Data           | Config option             |
+================+===========================+
| user data      | cloud-init.user-data      |
+----------------+---------------------------+
| vendor data    | cloud-init.vendor-data    |
+----------------+---------------------------+
| network config | cloud-init.network-config |
+----------------+---------------------------+

See the LXD `Instance Configuration`_ docs for more info about configuration
values or the LXD `Custom Network Configuration`_ document for more about
custom network config.

QEMU
====

The :command:`cloud-localds` command from the `cloud-utils`_ package generates
a disk with user-supplied data. The ``NoCloud`` datasouce allows users to
provide their own user data, metadata, or network configuration directly to
an instance without running a network service. This is helpful for launching
local cloud images with QEMU, for example.

The following is an example of creating the local disk using the
:command:`cloud-localds` command:

.. code-block:: shell-session

    $ cat >user-data <<EOF
    #cloud-config
    password: password
    chpasswd:
      expire: False
    ssh_pwauth: True
    ssh_authorized_keys:
      - ssh-rsa AAAA...UlIsqdaO+w==
    EOF
    $ cloud-localds seed.img user-data

The resulting :file:`seed.img` can then be passed along to a cloud image
containing ``cloud-init``. Below is an example of passing the :file:`seed.img`
with QEMU:

.. code-block:: shell-session

    $ qemu-system-x86_64 -m 1024 -net nic -net user \
        -hda ubuntu-20.04-server-cloudimg-amd64.img \
        -hdb seed.img

The now-booted image will allow for login using the password provided above.

For additional configuration, users can provide much more detailed
configuration, including network configuration and metadata:

.. code-block:: shell-session

    $ cloud-localds --network-config=network-config-v2.yaml \
      seed.img userdata.yaml metadata.yaml

See the :ref:`network_config_v2` page for details on the format and config of
network configuration. To learn more about the possible values for metadata,
check out the :ref:`datasource_nocloud` page.


.. _Multipass: https://multipass.run/
.. _LXD: https://linuxcontainers.org/
.. _QEMU: https://www.qemu.org/
.. _Instance Configuration: https://linuxcontainers.org/lxd/docs/master/instances
.. _Custom Network Configuration: https://linuxcontainers.org/lxd/docs/master/cloud-init
.. _cloud-utils: https://github.com/canonical/cloud-utils/
