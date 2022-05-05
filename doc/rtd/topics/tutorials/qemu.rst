.. _tutorial_qemu:

Qemu
****

In this tutorial, we will create our first cloud-init user data config and
deploy it into a Qemu_ virtual machine. We'll be using Qemu for this tutorial
which is a popular emulator for running virtual machines on Linux. Several
popular virtual machine tools use Qemu, including Libvirt, LXD, and Vagrant.

Install Qemu
============

.. code-block:: sh

    $ sudo apt install qemu-system-x86

See qemu's `install instructions <https://www.qemu.org/download/#linux>`_.

Download a Cloud Image
======================

All commands should be executed from a single directory; some
commands create files that are used by later commands. One might want to
use a temporary directory for easy clean up afterwards.

.. code-block:: sh

    $ wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img

Cloud images have cloud-init pre-installed.


Define our user data
====================

Create the following file ``user-data``.

.. code-block:: sh

    $ cat << EOF > user-data
    #cloud-config
    password: passw0rd
    chpasswd:
      expire: False

    EOF

Define our meta data
====================

Create the following file on your local filesystem at ``meta-data``.

.. code-block:: sh

    $ cat << EOF > meta-data
    instance-id: id-007
    local-hostname: jammy

    EOF


Define our vendor data
======================

Not necessary, but faster (retry wait time).

.. code-block:: sh

    $ touch vendor-data


Start an ad hoc IMDS Server
===========================

.. code-block:: sh

    $ python3 -m http.server --directory . &


Launch a vm with our user data
==============================

Now that we have LXD setup and our user data defined, we can launch an
instance with our user data:

.. code-block:: sh

    $ qemu-system-x86_64                                            \
        -net nic                                                    \
        -net user                                                   \
        -machine accel=kvm,type=q35                                 \
        -cpu host                                                   \
        -m 512                                                      \
        -nographic                                                  \
        -hda jammy-server-cloudimg-amd64.img                        \
        -smbios type=1,serial=ds='nocloud-net;s=http://10.0.2.2:8000/'


Verify that cloud-init ran successfully
=======================================

After launching the virtual machine, we should be able to connect
to our instance using the User: ``ubuntu`` and Password: ``passw0rd``

If you can log in using the configured password, it worked!

Check the cloud-init status:

.. code-block:: sh

    $ cloud-init status --wait
    .....
    cloud-init status: done


Tear down
=========

Exit the qemu shell using ``ctrl-a x`` (that's ctrl and a
simultaneously, followed by ``x``).

If you started the python webserver in the background (using ``&``),
then don't forget to bring it to the foreground (``fg``) and kill it
(``ctrl-c``).


What's next?
============

In this tutorial, we configured the default user's password.
The full list of modules available can be found in
:ref:`modules documentation<modules>`.
Each module contains examples of how to use it.

You can also head over to the :ref:`examples<yaml_examples>` page for
examples of more common use cases.

.. _Qemu: https://www.qemu.org
