.. _tutorial_qemu:

Core tutorial with QEMU
***********************

.. toctree::
   :titlesonly:
   :hidden:

   qemu-debugging.rst

In this tutorial, we will launch an Ubuntu cloud image in a virtual machine
that uses ``cloud-init`` to pre-configure the system during boot.

The goal of this tutorial is to provide a minimal demonstration of
``cloud-init``, which you can then use as a development environment to test
your ``cloud-init`` configurations locally before launching to the cloud.

Why QEMU?
=========

`QEMU`_ is a cross-platform emulator capable of running performant virtual
machines. QEMU is used at the core of a broad range of production operating
system deployments and open source software projects (including libvirt, LXD,
and vagrant) and is capable of running Windows, Linux, and Unix guest operating
systems. While QEMU is flexibile and feature-rich, we are using it because of
the broad support it has due to its broad adoption and ability to run on
\*nix-derived operating systems.

How to use this tutorial
========================

In this tutorial, the commands in each code block can be copied and pasted
directly into the terminal. Omit the prompt (``$``) before each command, or
use the "copy code" button on the right-hand side of the block, which will copy
the command for you without the prompt.

Each code block is preceded by a description of what the command does, and
followed by an example of the type of output you should expect to see.

Install QEMU
============

.. code-block:: sh

    $ sudo apt install qemu-system-x86

If you are not using Ubuntu, you can visit QEMU's `install instructions`_ for
additional information.

Create a temporary directory
============================

This directory will store our cloud image and configuration files for
:ref:`user data<user_data_formats>`, :ref:`metadata<instance_metadata>`, and
:ref:`vendor data<vendordata>`.

You should run all commands from this temporary directory. If you run the
commands from anywhere else, your virtual machine will not be configured.

Let's create a temporary directory and make it our current working directory
with :command:`cd`:

.. code-block:: sh

   $ mkdir temp
   $ cd temp

Download a cloud image
======================

Cloud images typically come with ``cloud-init`` pre-installed and configured to
run on first boot. You will not need to worry about installing ``cloud-init``
for now, since we are not manually creating our own image in this tutorial.

In our case, we want to select the latest Ubuntu LTS_. Let's download the
server image using :command:`wget`:

.. code-block:: sh

    $ wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img

Define our user data
====================

Now we need to create our :file:`user-data` file. This user data cloud-config
sets the password of the default user, and sets that password to never expire.
For more details you can refer to the
:ref:`Set Passwords module page<mod_cc_set_passwords>`.

Run the following command, which creates a file named :file:`user-data`
containing our configuration data.

.. code-block:: sh

    $ cat << EOF > user-data
    #cloud-config
    password: password
    chpasswd:
      expire: False

    EOF

What is user data?
==================

Before moving forward, let's inspect our :file:`user-data` file.

.. code-block:: sh

   $ cat user-data

You should see the following contents:

.. code-block:: yaml

    #cloud-config
    password: password
    chpasswd:
      expire: False

The first line starts with ``#cloud-config``, which tells ``cloud-init``
what type of user data is in the config. Cloud-config is a YAML-based
configuration type that tells ``cloud-init`` how to configure the virtual
machine instance. Multiple different format types are supported by
``cloud-init``. For more information, see the
:ref:`documentation describing different formats<user_data_formats>`.

The second line, ``password: password``, as per
:ref:`the Users and Groups module docs<mod_cc_users_groups>`, sets the default
user's password to ``password``.

The third and fourth lines direct ``cloud-init`` to not require a password
reset on first login.

Define our metadata
===================

Now let's run the following command, which creates a file named
:file:`meta-data` containing configuration data.

.. code-block:: sh

    $ cat << EOF > meta-data
    instance-id: someid/somehostname

    EOF

Define our vendor data
======================

Now we will create the empty file :file:`vendor-data` in our temporary
directory. This will speed up the retry wait time.

.. code-block:: sh

    $ touch vendor-data


Start an ad hoc IMDS webserver
==============================

Open up a second terminal window, change to your temporary directory and then
start the built-in Python webserver:

.. code-block:: sh

    $ cd temp
    $ python3 -m http.server --directory .

What is an IMDS?
----------------

Instance Metadata Service (IMDS) is a service provided by most cloud providers
as a means of providing information to virtual machine instances. This service
is used by cloud providers to expose information to a virtual machine. This
service is used for many different things, and is the primary mechanism for
some clouds to expose ``cloud-init`` configuration data to the instance.

How does ``cloud-init`` use the IMDS?
-------------------------------------

The IMDS uses a private http webserver to provide metadata to each operating
system instance. During early boot, ``cloud-init`` sets up network access and
queries this webserver to gather configuration data. This allows ``cloud-init``
to configure your operating system while it boots.

In this tutorial we are emulating this workflow using QEMU and a simple Python
webserver. This workflow is suitable for developing and testing
``cloud-init`` configurations prior to cloud deployments.

Launch a virtual machine with our user data
===========================================

Switch back to your original terminal, and run the following command so we can
launch our virtual machine. By default, QEMU will print the kernel logs and
``systemd`` logs to the terminal while the operating system boots. This may
take a few moments to complete.

.. code-block:: sh

    $ qemu-system-x86_64                                            \
        -net nic                                                    \
        -net user                                                   \
        -machine accel=kvm:tcg                                      \
        -cpu host                                                   \
        -m 512                                                      \
        -nographic                                                  \
        -hda jammy-server-cloudimg-amd64.img                        \
        -smbios type=1,serial=ds='nocloud;s=http://10.0.2.2:8000/'

.. note::
   If the output stopped scrolling but you don't see a prompt yet, press
   :kbd:`Enter` to get to the login prompt.

How is QEMU configured for ``cloud-init``?
------------------------------------------

When launching QEMU, our machine configuration is specified on the command
line. Many things may be configured: memory size, graphical output, networking
information, hard drives and more.

Let us examine the final two lines of our previous command. The first of them,
:command:`-hda jammy-server-cloudimg-amd64.img`, tells QEMU to use the cloud
image as a virtual hard drive. This will cause the virtual machine to
boot Ubuntu, which already has ``cloud-init`` installed.

The second line tells ``cloud-init`` where it can find user data, using the
:ref:`NoCloud datasource<datasource_nocloud>`. During boot, ``cloud-init``
checks the ``SMBIOS`` serial number for ``ds=nocloud``. If found,
``cloud-init`` will use the specified URL to source its user data config files.

In this case, we use the default gateway of the virtual machine (``10.0.2.2``)
and default port number of the Python webserver (``8000``), so that
``cloud-init`` will, inside the virtual machine, query the server running on
host.

Verify that ``cloud-init`` ran successfully
===========================================

After launching the virtual machine, we should be able to connect to our
instance using the default distro username.

In this case the default username is ``ubuntu`` and the password we configured
is ``password``.

If you can log in using the configured password, it worked!

If you couldn't log in, see
:ref:`this page for debug information<qemu_debug_info>`.

Check ``cloud-init`` status
===========================

Run the following command, which will allow us to check if ``cloud-init`` has
finished running:

.. code-block:: sh

    $ cloud-init status --wait

If you see ``status: done`` in the output, it succeeded!

If you see a failed status, you'll want to check
:file:`/var/log/cloud-init.log` for warning/error messages.

Tear down
=========

In our main terminal, let's exit the QEMU shell using :kbd:`ctrl-a x` (that's
:kbd:`ctrl` and :kbd:`a` simultaneously, followed by :kbd:`x`).

In the second terminal, where the Python webserver is running, we can stop the
server using (:kbd:`ctrl-c`).

What's next?
============

In this tutorial, we configured the default user's password and ran
``cloud-init`` inside our QEMU virtual machine.

The full list of modules available can be found in
:ref:`our modules documentation<modules>`.
The documentation for each module contains examples of how to use it.

You can also head over to the :ref:`examples page<yaml_examples>` for
examples of more common use cases.

.. _QEMU: https://www.qemu.org
.. _install instructions: https://www.qemu.org/download/#linux
.. _LTS: https://wiki.ubuntu.com/Releases
