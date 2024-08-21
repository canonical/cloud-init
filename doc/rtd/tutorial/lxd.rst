.. _tutorial_lxd:

Quick-start tutorial with LXD
*****************************

In this tutorial, we will create our first ``cloud-init`` user data script
and deploy it into an `LXD`_ container.

Why LXD?
========

We'll be using LXD for this tutorial because it provides first class support
for ``cloud-init`` user data, as well as ``systemd`` support. Because it is
container based, it allows us to quickly test and iterate upon our user data
definition.

How to use this tutorial
========================

In this tutorial, the commands in each code block can be copied and pasted
directly into the terminal. Omit the prompt (``$``) before each command, or
use the "copy code" button on the right-hand side of the block, which will copy
the command for you without the prompt.

Each code block is preceded by a description of what the command does, and
followed by an example of the type of output you should expect to see.

Install and initialise LXD
==========================

If you already have LXD set up, you can skip this section. Otherwise, let's
install LXD:

.. code-block:: shell-session

    $ sudo snap install lxd

If you don't have snap, you can install LXD using one of the
`other installation options`_.

Now we need to initialise LXD. The minimal configuration will be enough for
the purposes of this tutorial. If you need to, you can always change the
configuration at a later time.

.. code-block:: shell-session

   $ lxd init --minimal

Define our user data
====================

Now that LXD is set up, we can define our user data. Create the
following file on your local filesystem at :file:`/tmp/my-user-data`:

.. code-block:: yaml

    #cloud-config
    runcmd:
      - echo 'Hello, World!' > /var/tmp/hello-world.txt

Here, we are defining our ``cloud-init`` user data in the
:ref:`#cloud-config<user_data_formats>` format, using the
:ref:`runcmd module <mod_cc_runcmd>` to define a command to run. When applied,
it will write ``Hello, World!`` to :file:`/var/tmp/hello-world.txt` (as we
shall see later!).

Launch a LXD container with our user data
=========================================

Now that we have LXD set up and our user data defined, we can launch an
instance with our user data:

.. code-block:: shell-session

    $ lxc launch ubuntu:focal my-test --config=user.user-data="$(cat /tmp/my-user-data)"

Verify that ``cloud-init`` ran successfully
-------------------------------------------

After launching the container, we should be able to connect to our instance
using:

.. code-block:: shell-session

    $ lxc shell my-test

You should now be in a shell inside the LXD instance.

Before validating the user data, let's wait for ``cloud-init`` to complete
successfully:

.. code-block:: shell-session

    $ cloud-init status --wait

Which provides the following output:

.. code-block::

    status: done

Verify our user data
--------------------

Now we know that ``cloud-init`` has been successfully run, we can verify that
it received the expected user data we provided earlier:

.. code-block:: shell-session

    $ cloud-init query userdata

Which should print the following to the terminal window:

.. code-block::

    #cloud-config
    runcmd:
      - echo 'Hello, World!' > /var/tmp/hello-world.txt

We can also assert the user data we provided is a valid cloud-config:

.. code-block:: shell-session

    $ cloud-init schema --system --annotate

Which should print the following:

.. code-block::

    Valid schema user-data

Finally, let us verify that our user data was applied successfully:

.. code-block:: shell-session

    $ cat /var/tmp/hello-world.txt

Which should then print:

.. code-block::

    Hello, World!

We can see that ``cloud-init`` has received and consumed our user data
successfully!

Tear down
=========

Exit the container shell (by typing :command:`exit` or pressing :kbd:`ctrl-d`).
Once we have exited the container, we can stop the container using:

.. code-block:: shell-session

    $ lxc stop my-test

We can then remove the container completely using:

.. code-block:: shell-session

    $ lxc rm my-test

What's next?
============

In this tutorial, we used the :ref:`runcmd module <mod_cc_runcmd>` to execute a
shell command. The full list of modules available can be found in our
:ref:`modules documentation<modules>`.
Each module contains examples of how to use it.

You can also head over to the :ref:`examples page<yaml_examples>` for
examples of more common use cases.

.. _LXD: https://ubuntu.com/lxd
.. _other installation options: https://documentation.ubuntu.com/lxd/en/latest/installing/#other-installation-options
