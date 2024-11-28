.. _launch_lxd:

Run cloud-init locally with LXD
********************************

`LXD`_ offers a streamlined user experience for using Linux system containers.

Create your configuration
-------------------------

In this example we will create a file called ``user-data.yaml`` containing
a basic cloud-init configuration:

.. code-block:: shell-session

    $ cat >user-data.yaml <<EOF
    #cloud-config
    password: password
    chpasswd:
      expire: False
    ssh_pwauth: True
    EOF

Initialize a container
----------------------

With LXD, the following command initializes a container with the user data file
we just created:

.. code-block:: shell-session

    $ lxc init ubuntu-daily:jammy test-container
    $ lxc config set test-container user.user-data - < userdata.yaml
    $ lxc start test-container

To avoid the extra commands this can also be done at launch:

.. code-block:: shell-session

    $ lxc launch ubuntu-daily:jammy test-container --config=user.user-data="$(cat userdata.yaml)"

Finally, a profile can be set up with the specific data if you need to
launch this multiple times:

.. code-block:: shell-session

    $ lxc profile create dev-user-data
    $ lxc profile set dev-user-data user.user-data - < cloud-init-config.yaml
    $ lxc launch ubuntu-daily:jammy test-container -p default -p dev-user-data

LXD configuration types
-----------------------

The above examples all show how to pass user data. To pass other types of
configuration data use the configuration options specified below:

+----------------+---------------------------+
| Data           | Configuration option      |
+================+===========================+
| user data      | cloud-init.user-data      |
+----------------+---------------------------+
| vendor data    | cloud-init.vendor-data    |
+----------------+---------------------------+
| network config | cloud-init.network-config |
+----------------+---------------------------+

See the LXD `Instance Configuration`_ docs for more info about configuration
values or the LXD `Custom Network Configuration`_ document for more about
custom network config and using LXD with cloud-init.

.. LINKS
.. _LXD: https://ubuntu.com/lxd
.. _Instance Configuration: https://documentation.ubuntu.com/lxd/en/latest/instances/
.. _Custom Network Configuration: https://documentation.ubuntu.com/lxd/en/latest/cloud-init/

