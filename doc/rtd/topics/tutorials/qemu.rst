.. _tutorial_qemu:

Qemu Tutorial
*************

.. toctree::
   :titlesonly:
   :hidden:

   qemu-debugging.rst



In this tutorial, we will demonstrate launching an Ubuntu cloud image in a
virtual machine that uses cloud-init to pre-configure the system during boot.

The goal of this tutorial is to provide a minimal demonstration of cloud-init
that you can use as a development environment to test cloud-init
configurations locally prior to launching in the cloud.


Why Qemu?
=========

Qemu_ is a cross-platform emulator capable of running performant virtual
machines. Qemu is used at the core of a broad range of production operating
system deployments and open source software projects (including libvirt, LXD,
and vagrant) and is capable of running Windows, Linux, and Unix guest operating
systems. While Qemu is flexibile and feature-rich, we are using it because of
the broad support it has due to its broad adoption and ability to run on
\*nix-derived operating systems.


What is an IMDS?
================

Instance Metadata Service is a service provided by most cloud providers as a
means of providing information to virtual machine instances. This service is
used by cloud providers to surface information to a virtual machine. This
service is used for many different things, and is the primary mechanism for
some clouds to expose cloud-init configuration data to the instance.


How does cloud-init use the IMDS?
=================================

The IMDS uses a private http webserver to provide metadata to each operating
system instance. During early boot, cloud-init sets up network access and
queries this webserver to gather configuration data. This allows cloud-init to
configure your operating system while it boots.

In this tutorial we emulate this workflow using Qemu and a simple python
webserver. This workflow may be suitable for developing and testing cloud-init
configurations prior to cloud deployments.


How to use this tutorial
========================

In this tutorial each code block is to be copied and pasted directly
into the terminal then executed. Omit the prompt ``$`` before each command.

Each code block is preceded by a description of what the command does.


Install Qemu
============

Install Qemu.

.. code-block:: sh

    $ sudo apt install qemu-system-x86

If you are not using Ubuntu, you can visit Qemu's `install instructions`_ for
additional information.


Create a temporary directory
============================

This directory will store our cloud image and configuration files for
:ref:`user-data<user_data_formats>`, :ref:`meta-data<instance_metadata>`, and
:ref:`vendor-data<vendordata>`

This tutorial expects that you run all commands from this temporary
directory. Failure to do so will result in an unconfigured virtual
machine.

Create a temporary directory and make it your current working directory with
``cd``.

.. code-block:: sh

   $ mkdir temp
   $ cd temp


Download a cloud image
======================

Cloud images typically come with cloud-init pre-installed and configured to run
on first boot. Users should not need to worry about installing cloud-init
unless they are manually creating their own images. In this case we select the
latest Ubuntu LTS_.

Download the server image using ``wget``.

.. code-block:: sh

    $ wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img


Define our user data
====================

Create the following file ``user-data``. This user-data cloud-config
sets the password of the default user and sets it to never expire. For
more details see this module_.

Execute the following command, which creates a file named ``user-data`` with
configuration data.

.. code-block:: sh

    $ cat << EOF > user-data
    #cloud-config
    password: password
    chpasswd:
      expire: False

    EOF


What is user data?
==================

Before moving forward, let's inspect our user data file.

.. code-block:: sh

   $ cat user-data

You should see the following contents:

.. code-block:: yaml

    #cloud-config
    password: password
    chpasswd:
      expire: False

The first line starts with ``#cloud-config``, which tells cloud-init
what kind of configuration is contained. The cloud-config config type uses YAML
format to tell cloud-init how to configure the virtual machine instance.
Multiple different formats are supported by cloud-init. See the
:ref:`documentation describing different formats<user_data_formats>`.

The second line, ``password: password``, per :ref:`the docs<mod-users_groups>`,
sets the default user's password to ``password``.

The third and fourth lines direct cloud-init to set this default password to
never expire.

Define our meta data
====================

Execute the following command, which creates a file named ``meta-data`` with
configuration data.

.. code-block:: sh

    $ cat << EOF > meta-data
    instance-id: someid/somehostname
    local-hostname: jammy

    EOF


Define our vendor data
======================

Now create the empty file ``vendor-data`` in your temporary directory. This
will speed up the retry wait time.

.. code-block:: sh

    $ touch vendor-data


Start an ad hoc IMDS Server
===========================

In a separate terminal, change to your temporary directory and then start the
python webserver (built-in to python).

.. code-block:: sh

    $ cd temp
    $ python3 -m http.server --directory .


Launch a virtual machine with our user data
===========================================

Launch the virtual machine. By default, Qemu will print the kernel logs
and systemd logs to the terminal while the operating system boots. This
may take a few moments to complete.

If the output stopped scrolling but you don't see a prompt yet, press ``enter``
to get to login prompt.


.. code-block:: sh

    $ qemu-system-x86_64                                            \
        -net nic                                                    \
        -net user                                                   \
        -machine accel=kvm:tcg                                      \
        -cpu host                                                   \
        -m 512                                                      \
        -nographic                                                  \
        -hda jammy-server-cloudimg-amd64.img                        \
        -smbios type=1,serial=ds='nocloud-net;s=http://10.0.2.2:8000/'


Verify that cloud-init ran successfully
=======================================

After launching the virtual machine we should be able to connect to our
instance using the default distro username.

In this case the default username is ``ubuntu`` and the password we configured
is ``password``.

If you can log in using the configured password, it worked!

If you cloudn't log in, see
:ref:`this page for debug information<qemu_debug_info>`.


Check cloud-init status
=======================

.. code-block:: sh

    $ cloud-init status --wait

If you see ``status: done`` in the output, it succeeded!

If you see a failed status, you'll want to check ``/var/log/cloud-init.log``
for warning/error messages.


Tear down
=========

Exit the Qemu shell using ``ctrl-a x`` (that's ``ctrl`` and ``a``
simultaneously, followed by ``x``).

Stop the python webserver that was started in a different terminal
(``ctrl-c``).


What's next?
============

In this tutorial, we configured the default user's password.
The full list of modules available can be found in
:ref:`modules documentation<modules>`.
The documentation for each module contains examples of how to use it.

You can also head over to the :ref:`examples<yaml_examples>` page for
examples of more common use cases.

.. _Qemu: https://www.qemu.org
.. _module: https://cloudinit.readthedocs.io/en/latest/topics/modules.html#set-passwords
.. _install instructions: https://www.qemu.org/download/#linux
.. _LTS: https://wiki.ubuntu.com/Releases
