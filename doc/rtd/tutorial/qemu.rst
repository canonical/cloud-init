.. _tutorial_qemu:

New user tutorial with QEMU
***************************

.. toctree::
   :titlesonly:
   :hidden:

   qemu-debugging.rst

In this tutorial, we will launch an Ubuntu cloud image in a virtual machine
that uses cloud-init to pre-configure the system during boot.

The goal of this tutorial is to provide a minimal demonstration of
cloud-init, which you can then use as a development environment to test
your cloud-init configuration locally before launching it to the cloud.

Why QEMU?
=========

`QEMU`_ is a cross-platform emulator capable of running performant virtual
machines. QEMU is used at the core of a range of production operating system
deployments and open source software projects (including libvirt, LXD,
and vagrant). It is capable of running Windows, Linux, and Unix guest operating
systems. While QEMU is flexible and feature-rich, we are using it because it
is widely supported and able to run on \*nix-derived operating systems.

If you do not already have QEMU installed, you can install it by running the
following command in Ubuntu:

.. code-block:: bash

    $ sudo apt install qemu-system-x86

If you are not using Ubuntu, you can visit QEMU's `install instructions`_ to
see details for your system.

Download a cloud image
======================

First, we'll set up a temporary directory that will store both our cloud image
and the configuration files we'll create in the next section. Let's also make
it our current working directory:

.. code-block:: bash

   $ mkdir temp
   $ cd temp

We will run all the commands from this temporary directory. If we run the
commands from anywhere else, our virtual machine will not be configured.

Cloud images typically come with cloud-init pre-installed and configured to
run on first boot. We don't need to worry about installing cloud-init
for now, since we are not manually creating our own image in this tutorial.

In our case, we want to select the latest `Ubuntu LTS`_. Let's download the
server image using :command:`wcurl`:

.. code-block:: bash

    $ wcurl https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img

.. note::
   This example uses emulated CPU instructions on non-x86 hosts, so it may be
   slow. To make it faster on non-x86 architectures, one can change the image
   type and ``qemu-system-<arch>`` command name to match the
   architecture of your host machine.

Define the configuration data files
===================================

When we launch an instance using cloud-init, we pass different types of
configuration data files to it. Cloud-init uses these as a blueprint for how to
configure the virtual machine instance. There are three major types:

* :ref:`user-data <user_data_formats>` is provided by the user, and cloud-init
  recognizes many different formats.
* :ref:`vendor-data <vendor-data>` is provided by the cloud provider.
* :ref:`meta-data <instance-data>` contains the platform data, including
  things like machine ID, hostname, etc.

There is a specific user-data format called "*cloud-config*" that is probably
the most commonly used, so we will create an example of this (and examples of
both vendor-data and meta-data files), then pass them all to cloud-init.

Let's create our :file:`user-data` file first. The user-data *cloud-config*
is a YAML-formatted file, and in this example it sets the password of the
default user, and sets that password to never expire. For more details you can
refer to the :ref:`Set Passwords module page<mod_cc_set_passwords>`.

Run the following command to create the user-data file (named
:file:`user-data`) containing our configuration data.

.. code-block:: bash

    $ cat << EOF > user-data
    #cloud-config
    password: password
    chpasswd:
      expire: False

    EOF

Before moving forward, let's first inspect our :file:`user-data` file.

.. code-block:: bash

    cat user-data

You should see the following contents:

.. code-block:: yaml

    #cloud-config
    password: password
    chpasswd:
      expire: False

* The first line starts with ``#cloud-config``, which tells cloud-init what
  type of user-data is in the config file.

* The second line, ``password: password`` sets the default user's password to
  ``password``, as per the :ref:`Users and Groups <mod_cc_users_groups>`
  module documentation.

* The third and fourth lines tell cloud-init not to require a password reset
  on first login.

Now let's run the following command, which creates a file named
:file:`meta-data` containing the instance ID we want to associate to the
virtual machine instance.

.. code-block:: bash

    $ cat << EOF > meta-data
    instance-id: someid/somehostname

    EOF

Next, let's create an empty file called :file:`vendor-data` in our temporary
directory. This will speed up the retry wait time.

.. code-block:: bash

    $ touch vendor-data


Start an ad hoc IMDS webserver
==============================

Instance Metadata Service (IMDS) is a service used by most cloud providers
as a way to expose information to virtual machine instances. This service is
the primary mechanism for some clouds to expose cloud-init configuration data
to the instance.

The IMDS uses a private http webserver to provide instance-data to each running
instance. During early boot, cloud-init sets up network access and queries this
webserver to gather configuration data. This allows cloud-init to configure
the operating system while it boots.

In this tutorial we are emulating this workflow using QEMU and a simple Python
webserver. This workflow is suitable for developing and testing cloud-init
configurations before deploying to a cloud.

Open up a second terminal window, and in that window, run the following
commands to change to the temporary directory and then start the built-in
Python webserver:

.. code-block:: bash

    $ cd temp
    $ python3 -m http.server --directory .

Launch a VM with our user-data
===============================

Switch back to your original terminal, and run the following command to launch
our virtual machine. By default, QEMU will print the kernel logs and
``systemd`` logs to the terminal while the operating system boots. This may
take a few moments to complete.

.. code-block:: bash

    $ qemu-system-x86_64                                            \
        -net nic                                                    \
        -net user                                                   \
        -machine accel=kvm:tcg                                      \
        -m 512                                                      \
        -nographic                                                  \
        -hda noble-server-cloudimg-amd64.img                        \
        -smbios type=1,serial=ds='nocloud;s=http://10.0.2.2:8000/'

.. note::
   If the output stopped scrolling but you don't see a prompt yet, press
   :kbd:`Enter` to get to the login prompt.

When launching QEMU, our machine configuration is specified on the command
line. Many things may be configured: memory size, graphical output, networking
information, hard drives and more.

Let us examine the final two lines of our previous command. The first of them,
:command:`-hda noble-server-cloudimg-amd64.img`, tells QEMU to use the cloud
image as a virtual hard drive. This will cause the virtual machine to
boot Ubuntu, which already has cloud-init installed.

The second line tells cloud-init where it can find user-data, using the
:ref:`NoCloud datasource<datasource_nocloud>`. During boot, cloud-init
checks the ``SMBIOS`` serial number for ``ds=nocloud``. If found,
cloud-init will use the specified URL to source its user-data config files.

In this case, we use the default gateway of the virtual machine (``10.0.2.2``)
and default port number of the Python webserver (``8000``), so that
cloud-init will, inside the virtual machine, query the server running on
host.

Verify that cloud-init ran successfully
===========================================

After launching the virtual machine, we should be able to connect to our
instance using the default distro username.

In this case the default username is ``ubuntu`` and the password we configured
is ``password``.

If you can log in using the configured password, it worked!

If you couldn't log in, see
:ref:`this page for debug information<qemu_debug_info>`.

Let's now check cloud-init's status. Run the following command, which will
allow us to check if cloud-init has finished running:

.. code-block:: bash

    $ cloud-init status --wait

If you see ``status: done`` in the output, it succeeded!

If you see a failed status, you'll want to check
:file:`/var/log/cloud-init.log` for warning/error messages.

Completion and next steps
=========================

In our main terminal, let's exit the QEMU shell using :kbd:`Ctrl-A X` (that's
:kbd:`Ctrl` and :kbd:`A` simultaneously, followed by :kbd:`X`).

In the second terminal, where the Python webserver is running, we can stop the
server using (:kbd:`Ctrl-C`).

In this tutorial, we configured the default user's password and ran
cloud-init inside our QEMU virtual machine.

The full list of modules available can be found in
:ref:`our modules documentation<modules>`.
The documentation for each module contains examples of how to use it.

You can also head over to the :ref:`examples page<yaml_examples>` for
examples of more common use cases.

.. _QEMU: https://www.qemu.org
.. _install instructions: https://www.qemu.org/download/#linux
.. _Ubuntu LTS: https://wiki.ubuntu.com/Releases
