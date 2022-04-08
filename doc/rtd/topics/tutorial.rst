.. _lxd_tutorial:

Tutorial
********

In this tutorial, we will create our first cloud-init user data script
and deploy it into an LXD container. We'll be using LXD_ for this tutorial
because it provides first class support for cloud-init user data as well as
systemd support. Because it is container based, it allows for quick
testing and iterating on our user data definition.

Setup LXD
=========

Skip this section if you already have LXD_ setup.

Install LXD
-----------

.. code-block:: shell-session

    $ sudo snap install lxd

If you don't have snap, you can install LXD using one of the
`other installation options`_.

Initialize LXD
--------------

.. code-block:: shell-session

  $ lxd init --minimal

The minimal configuration should work fine for our purposes. It can always
be changed at a later time if needed.

Define our user data
====================

Now that LXD is setup, we can define our user data. Create the
following file on your local filesystem at ``/tmp/my-user-data``:

.. code-block:: yaml

    #cloud-config
    runcmd:
      - echo 'Hello, World!' > /var/tmp/hello-world.txt

Here we are defining our cloud-init user data in the
:ref:`cloud-config<cloud Config Data>` format, using the `runcmd`_ module to
define a command to run. When applied, it
should write ``Hello, World!`` to ``/var/tmp/hello-world.txt``.

Launch a container with our user data
=====================================

Now that we have LXD setup and our user data defined, we can launch an
instance with our user data:

.. code-block:: shell-session

    $ lxc launch ubuntu:focal my-test --config=user.user-data="$(cat /tmp/my-user-data)"

Verify that cloud-init ran successfully
=======================================

After launching the container, we should be able to connect
to our instance using

.. code-block:: shell-session

    $ lxc shell my-test

You should now be in a shell inside the LXD instance.
Before validating the user data, let's wait for cloud-init to complete
successfully:

.. code-block:: shell-session

    $ cloud-init status --wait
    .....
    cloud-init status: done
    $

We can now verify that cloud-init received the expected user data:

.. code-block:: shell-session

    $ cloud-init query userdata
    #cloud-config
    runcmd:
      - echo 'Hello, World!' > /var/tmp/hello-world.txt

We can also assert the user data we provided is a valid cloud-config:

.. code-block:: shell-session

    $ cloud-init devel schema --system --annotate
    Valid cloud-config: system userdata
    $

Finally, verify that our user data was applied successfully:

.. code-block:: shell-session

    $ cat /var/tmp/hello-world.txt
    Hello, World!
    $

We can see that cloud-init has consumed our user data successfully!

Tear down
=========

Exit the container shell (i.e., using ``exit`` or ctrl-d). Once we have
exited the container, we can stop the container using:

.. code-block:: shell-session

    $ lxc stop my-test

and we can remove the container using:

.. code-block:: shell-session

    $ lxc rm my-test

What's next?
============

In this tutorial, we used the runcmd_ module to execute a shell command.
The full list of modules available can be found in
:ref:`modules documentation<modules>`.
Each module contains examples of how to use it.

You can also head over to the :ref:`examples<yaml_examples>` page for
examples of more common use cases.

.. _LXD: https://linuxcontainers.org/lxd/
.. _other installation options: https://linuxcontainers.org/lxd/getting-started-cli/#other-installation-options
.. _runcmd: https://cloudinit.readthedocs.io/en/latest/topics/modules.html#runcmd
