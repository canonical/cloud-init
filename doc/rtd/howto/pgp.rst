.. _pgp:

Use encrypted or signed user data
*********************************

Overview
========

This guide will show you how to use PGP encryption to secure your
:ref:`user data<user_data_formats-pgp>`
when using cloud-init. This will be accomplished with the following steps:

1. Launch a cloud instance
2. Generate PGP key pairs
3. Encrypt and sign the user data
4. Export the keys
5. Restrict user data to require PGP message
6. Retrieve our encrypted and signed user data
7. Create a custom image containing the keys
8. Launch an instance with the encrypted user data

We will be using the `gpg` command to for all PGP-related operations. This
guide will add new keys to the default key ring while later providing
instructions for removing them. These keys are generated for instructive
purposes only and are not intended for production use.

.. note::
    This guide is NOT intended to be a comprehensive guide to PGP encryption or
    best practices when using the `gpg` command or gpg key rings. Please
    consult the `GnuPG documentation <https://gnupg.org/>`_ for documentation
    and best practices.

Prerequisites
=============

This guide also assumes you have the ability to launch cloud instances
with root permissions and can create snapshots or custom images from
those instances. This guide will demonstrate this using LXD, but
commands to achieve the same result will vary by cloud provider.

The launched instance must contain the `GNU Privacy Guard` software
which provides the `gpg` command.

Launch a cloud instance
=======================

We will use LXD to launch an Ubuntu instance, but you can use any cloud
provider and OS that supports `gpg` and cloud-init.

Launch the instance and connect to it:

.. code-block:: bash

    $ lxc launch ubuntu:noble pgp-demo
    $ lxc shell pgp-demo

You should now be inside the LXD instance in the "/root" directory.
The remaining steps will be performed inside this instance in the "/root"
directory until otherwise noted.

Generate PGP key pairs
======================

.. note::

    If you already have PGP key pairs you would like to use, you can skip this
    step. However, we do NOT recommend reusing or sharing any personal
    private keys.

First, generate a new key pair to be used for signing:

.. code-block:: bash

    $ gpg --quick-generate-key --batch --passphrase "" signing_user

Next, generate a new key pair to be used for encryption:

.. code-block:: bash

    $ gpg --quick-generate-key --batch --passphrase "" encrypting_user

Encrypt and sign the user data
==============================

Create a file with your user data. For this example, we will use a simple
cloud-config file:

.. code-block:: yaml

    #cloud-config
    runcmd:
      - echo 'Hello, World!' > /var/tmp/hello-world.txt

Save this file to your working directory as `cloud-config.yaml`.

Encrypt the user data using the public key of the encrypting user and
sign it using the private key of the signing user:

.. code-block:: bash

    $ gpg --batch --output cloud-config.yaml.asc --sign --local-user signing_user --encrypt --recipient encrypting_user --armor cloud-config.yaml

Our encrypted and signed user data is now saved in `cloud-config.yaml.asc`.

Export the keys
===============

In order to use this user data, we will need to create a custom image
containing the public key of the encrypting user and the private key
of the signing user.

Create the key directory:

.. code-block:: bash

    $ mkdir /etc/cloud/keys

Export the public key of the signing user:

.. code-block:: bash

    $ gpg --export signing_user > /etc/cloud/keys/signing_user.gpg

Export the private key of the encrypting user:

.. code-block:: bash

    $ gpg --export-secret-keys encrypting_user > /etc/cloud/keys/encrypting_user.gpg

Why export keys?
----------------

While it is more steps to export the keys in this way as opposed to
using the existing key ring in the snapshot, we do this for a few reasons:

* Users may not want these keys in any key ring by default on a new instance
* Exporting keys is easier than copying key rings

Note that on launch, cloud-init will import these keys into a temporary
key ring that is removed after the user data is processed. The default
key ring will not be read or modified.

Restrict user data to require PGP message
=========================================

To ensure that our message hasn't been replaced or tampered with, we can
require that cloud-init only process PGP messages. To do so, create a file
`/etc/cloud/cloud.cfg.d/99_pgp.cfg` with the following contents:

.. code-block:: text

    user_data:
      require_signature: true

Retrieve our encrypted and signed user data
===========================================

Before running
these commands, copy the encrypted and signed user data
that we created earlier to the host system.

From the host system, run:

.. code-block:: bash

    $ lxc file pull pgp-demo/root/cloud-config.yaml.asc .


Create a custom image containing the keys
=========================================

.. note::
    Before creating the image, you may want to remove the original user data
    and created key ring from the instance. This is not strictly necessary
    but is recommended for a clean image.

Now that we have our instance configured, we can create a custom image from
it. This step will vary depending on your cloud provider.

Using LXD, from the host system, run:

.. code-block:: bash

    $ lxc stop pgp-demo
    $ lxc publish pgp-demo --alias pgp-demo-image

Launch an instance with the encrypted user data
===============================================

Now that we have our custom image with the keys, we can launch a
new instance with the encrypted user data. With your encrypted and signed
user data in the current working directory, run:

.. code-block:: bash

    $ lxc launch pgp-demo-image pgp-demo-encrypted \
      --config user.user-data="$(cat cloud-config.yaml.asc)"

On the launched system, you should see the file `/var/tmp/hello-world.txt`
containing the text `Hello, World!`.
