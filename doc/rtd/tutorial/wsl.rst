.. _tutorial_wsl:

WSL Tutorial
************

In this tutorial, we will customize a Windows Subsystem for Linux (WSL)
instance using cloud-init on Ubuntu.

How to use this tutorial
========================

In this tutorial, the commands in each code block can be copied and pasted
directly into a ``PowerShell`` Window . Omit the prompt before each
command, or use the "copy code" button on the right-hand side of the block,
which will copy the command for you without the prompt.

Prerequisites
=============

This tutorial assumes you are running within a ``Windows 11`` or ``Windows
Server 2022`` environment. If ``wsl`` is already installed, you must be
running version 2. You can check your version of ``wsl`` by running the
following command:

.. code-block:: doscon

    PS> wsl --version

Example output:

.. code-block:: text

    WSL version: 2.1.5.0
    Kernel version: 5.15.146.1
    WSLg version: 1.0.60
    MSRDC version: 1.2.5105
    Direct3D version: 1.611.1-81528511
    DXCore version: 10.0.25131.1002-220531-1700.rs-onecore-base2-hyp
    Windows version: 10.0.20348.2402

If running this tutorial within a virtualized
environment (`including in the cloud`_), ensure that
`nested virtualization`_ is enabled.

Install WSL
===========

.. note::
    If you have already installed WSL, you can skip this section.

.. code-block:: doscon

    PS> wsl --install

Example output:

.. code-block:: text

    Installing: Virtual Machine Platform
    Virtual Machine Platform has been installed.
    Installing: Windows Subsystem for Linux
    Windows Subsystem for Linux has been installed.
    Installing: Ubuntu
    Ubuntu has been installed.
    The requested operation is successful. Changes will not be effective until the system is rebooted.

Reboot the system when prompted.

Obtain the Ubuntu WSL image
===========================

Ubuntu 24.04 is the first Ubuntu version to support cloud-init in WSL,
so that is the image that we'll use.

We have two options to obtain the Ubuntu 24.04 WSL image: the Microsoft
Store and the Ubuntu image server.

Option #1: The Microsoft Store
------------------------------

If you have access to the Microsoft Store, you can download the
`Ubuntu 24.04`_ WSL image from within the app.

Click on the "Get" button to download the image.

Once the image has downloaded, do **NOT** click open as that
will start the instance before we have defined our cloud-init user data
used to customize the instance.

Once the image has downloaded, you can verify that it is available by
running the following command:

.. code-block:: doscon

    PS> wsl --list

Example output:

.. code-block:: text

    Windows Subsystem for Linux Distributions:
    Ubuntu (Default)
    Ubuntu-24.04

It should show ``Ubuntu-24.04`` in the list of available WSL instances.

Option #2: The Ubuntu image server
----------------------------------

If the Microsoft Store is not an option, we can instead download the
Ubuntu 24.04 WSL image from the `Ubuntu image server`_.

Create a directory under the user's home directory to store the
WSL image and install data.

.. code-block:: doscon

    PS> mkdir ~\wsl-images

Download the Ubuntu 24.04 WSL image.

.. code-block:: doscon

    PS> Invoke-WebRequest -Uri https://cloud-images.ubuntu.com/wsl/noble/current/ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz -OutFile wsl-images\ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz

Import the image into WSL storing it in the ``wsl-images`` directory.

.. code-block:: doscon

    PS> wsl --import Ubuntu-24.04 wsl-images .\wsl-images\ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz

Example output:

.. code-block::

    Import in progress, this may take a few minutes.
    The operation completed successfully.

Create our user data
====================

User data is the primary way for a user to customize a cloud-init instance.
Open Notepad and paste the following:

.. code-block:: yaml

    #cloud-config
    write_files:
    - content: |
        Hello from cloud-init
      path: /var/tmp/hello-world.txt
      permissions: '0777'

Save the file to ``%USERPROFILE%\.cloud-init\Ubuntu-24.04.user-data``.

For example, if your username is ``me``, the path would be
``C:\Users\me\.cloud-init\Ubuntu-24.04.user-data``.
Ensure that the file is saved with the ``.user-data`` extension and
not as a ``.txt`` file.

.. note::
    We are creating user data that is tied to the instance we just created,
    but by changing the filename, we can create user data that applies to
    multiple or all WSL instances. See
    :ref:`WSL Datasource reference page<wsl_user_data_configuration>` for
    more information.

What is user data?
==================

Before moving forward, let's inspect our :file:`user-data` file.

We created the following contents:

.. code-block:: yaml

    #cloud-config
    write_files:
    - content: |
        Hello from cloud-init
      path: /var/tmp/hello-world.txt
      permissions: '0770'

The first line starts with ``#cloud-config``, which tells cloud-init
what type of user data is in the config. Cloud-config is a YAML-based
configuration type that tells cloud-init how to configure the instance
being created. Multiple different format types are supported by
cloud-init. For more information, see the
:ref:`documentation describing different formats<user_data_formats>`.

The remaining lines, as per
:ref:`the Write Files module docs<mod_cc_write_files>`, creates a file
``/var/tmp/hello-world.txt`` with the content ``Hello from cloud-init`` and
permissions allowing anybody on the system to read or write the file.

Start the Ubuntu WSL instance
=============================

.. code-block:: doscon

    PS> wsl --distribution Ubuntu-24.04

The Ubuntu WSL instance will start, and you may be prompted for a username
and password.

.. code-block:: text

    Installing, this may take a few minutes...
    Please create a default UNIX user account. The username does not need to match your Windows username.
    For more information visit: https://aka.ms/wslusers
    Enter new UNIX username:
    New password:
    Retype new password:

Once the credentials have been entered, you should see a welcome
screen similar to the following:

.. code-block:: text

    Welcome to Ubuntu Noble Numbat (GNU/Linux 5.15.146.1-microsoft-standard-WSL2 x86_64)

    * Documentation:  https://help.ubuntu.com
    * Management:     https://landscape.canonical.com
    * Support:        https://ubuntu.com/pro

    System information as of Mon Apr 22 21:06:49 UTC 2024

    System load:  0.08                Processes:             51
    Usage of /:   0.1% of 1006.85GB   Users logged in:       0
    Memory usage: 4%                  IPv4 address for eth0: 172.29.240.255
    Swap usage:   0%


    This message is shown once a day. To disable it please create the
    /root/.hushlogin file.
    root@machine:/mnt/c/Users/me#

You should now be in a shell inside the WSL instance.

Verify that ``cloud-init`` ran successfully
-------------------------------------------

Before validating the user data, let's wait for ``cloud-init`` to complete
successfully:

.. code-block:: shell-session

    $ cloud-init status --wait

Which provides the following output:

.. code-block:: text

    status: done

Now we can now see that cloud-init has detected that we running in WSL:

.. code-block:: shell-session

    $ cloud-id

Which provides the following output:

.. code-block:: text

    wsl

Verify our user data
--------------------

Now we know that ``cloud-init`` has been successfully run, we can verify that
it received the expected user data we provided earlier:

.. code-block:: shell-session

    $ cloud-init query userdata

Which should print the following to the terminal window:

.. code-block::

    #cloud-config
    write_files:
    - content: |
        Hello from cloud-init
    path: /var/tmp/hello-world.txt
    permissions: '0770'

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

    Hello from cloud-init

We can see that ``cloud-init`` has received and consumed our user data
successfully!

What's next?
============

In this tutorial, we used the :ref:`Write Files module <mod_cc_write_files>` to
write a file to our WSL instance. The full list of modules available can be
found in our :ref:`modules documentation<modules>`.
Each module contains examples of how to use it.

You can also head over to the :ref:`examples page<yaml_examples>` for
examples of more common use cases.

Cloud-init's WSL reference documentation can be found on the
:ref:`WSL Datasource reference page<datasource_wsl>`.


.. _including in the cloud: https://techcommunity.microsoft.com/t5/itops-talk-blog/how-to-setup-nested-virtualization-for-azure-vm-vhd/ba-p/1115338
.. _nested virtualization: https://docs.microsoft.com/en-us/virtualization/hyper-v-on-windows/user-guide/nested-virtualization
.. _Ubuntu 24.04: https://apps.microsoft.com/detail/9nz3klhxdjp5
.. _Ubuntu image server: https://cloud-images.ubuntu.com/wsl/
