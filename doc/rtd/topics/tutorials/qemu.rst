.. _tutorial_qemu:

Qemu Tutorial
*************

In this tutorial, we will create our first cloud-init user data config and
deploy it into a Qemu_ virtual machine. We'll be using Qemu for this tutorial
which is a popular emulator for running virtual machines on Linux. Several
popular virtual machine tools use Qemu, including Libvirt, LXD, and Vagrant.

What is an IMDS?
================

Many cloud providers supply a private http webserver to each operating
system instance launched. During early boot, cloud-init sets up network
access and queries this webserver to gather configuration data. This allows
cloud-init to configure your operating system while it boots.

In this tutorial we emulate this workflow using Qemu and a simple python
webserver. This workflow may be suitable for developing and testing cloud-init
configurations prior to cloud deployments.

How to use this tutorial:
=========================

In this tutorial each code block is to be copied and pasted directly
into the terminal then executed. Omit the prompt `$` before each command.

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

This directory will store our cloud image and configuration files,
``meta-data`` [add-link], ``vendor-data`` [add-link], and ``user-data``
[add-link],

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

Define our meta data
====================

Execute the following command, which creates a file named ``meta-data`` with
configuration data.

.. code-block:: sh

    $ cat << EOF > meta-data
    instance-id: jammy-01
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

Launch the virtual machine. By default, qemu will print to the terminal both
kernel logs and systemd logs while the operating system boots. This may take a
few moments to complete.

If the output stopped scrolling but you don't see a prompt yet, type ``enter``
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

Check the cloud-init status:

.. code-block:: sh

    $ cloud-init status --wait
    .....
    cloud-init status: done


Debugging tips
==============

If you successfully launched the virtual machine, but couldn't log in,
there are a few places to check to debug your setup.

- The webserver should print out a message for each request it receives.
  If it didn't print out any messages when the virtual machine booted,
  then cloud-init was unable to obtain the config. Make sure that the
  webserver can be locally accessed using ``curl`` or ``wget``.

.. code-block:: sh

   $ curl 0.0.0.0:8000/user-data
   $ curl 0.0.0.0:8000/meta-data
   $ curl 0.0.0.0:8000/vendor-data

- When launching Qemu, if the webserver prints out 404 errors, then try to
  figure out why those files can't be served (did you forget to start the
  server in the temp directory?)
  

- When launching Qemu, if the webserver shows that it succeeded in serving
  ``user-data``, ``meta-data``, and ``vendor-data``, but you cannot log
  in, then you may have provided incorrect cloud-config files.


  If you do not see any new output, then cloud-init didn't discover its
  datasource correctly.


   If you cannot hit these files, figure out why (verify they exist
   where the python webserver is running, check your local firewall, etc)



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
