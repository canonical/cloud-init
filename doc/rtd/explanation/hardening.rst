Security Hardening
******************

Cloud-init's use case is automating cloud instance initialization, with support
across distributions and platforms. There is a myriad of ways to harden this
space.

Follow the security hardening guidelines provided by the OSes and cloud
platforms that your cloud-init configuration is targeting.

Many cloud platforms provide SSH public keys in metadata which setup the
default user with the appropriate configured means of access using
SSH public/private key pairs.


Updated packages
================

To ensure the available security fixes are applied to you VMs images upon
launch, it is recommended to update the packages

.. note::

  Ubuntu cloud images are configured by default to enable unattended-upgrades,
  thus this is resolved this issue when the update gets triggered. One can
  still apply this recommendation to cloud that gap and update the packages
  on first boot.

.. code-block:: yaml

  #cloud-config
  package_update: true
  package_upgrade: true


Ubuntu's security guidelines: https://documentation.ubuntu.com/server/explanation/security/security_suggestions/#keep-your-system-up-to-date

No plain text passwords
=======================

Most of the harmful security exposure comes when custom user-data presented
as ``#cloud-config`` or run scripts by the end-user at VM launch time which
provides credentials in the form of clear passwords or credentials encoded in
URLs for services.

It is advised to not provide clear-text passwords or credentials in any
``runcmd`` / ``bootcmd`` or user-data scripts #/bin/bash, etc because that
config user-data may be accessible to others on a local network based on a
given cloud platform's instance metadata service and instead obtain those
credentials to service-endpoints from a vault service or configuration
management service such as Puppet, Chef, Ansible, Saltstack, etc.

While creating users with the
:ref:`Users and Groups module <mod_cc_users_groups>`, do not use the
``user.plain_text_passwd`` key with its associated value as plain text.
``hashed_passwd`` is a more secure alternative.

Avoid plain text passwords with the
:ref:`Set Passwords <mod_cc_set_passwords>`.

Alternatives to user passwords
------------------------------

We recommend using the :ref:`SSH module <mod_cc_ssh>` with ``ssh_import_id`` or
``ssh_authorized_keys`` to import public SSH keys.



More info:
https://documentation.ubuntu.com/server/how-to/security/openssh-server/#ssh-keys

SSH Host keys
=============

Cloud-init publishes the SSH host public keys generated to the serial console
which can be validated prior to any SSH client connection to the launched VM.

It provides assurance that you are connecting to the virtual machine you
intended to launch, and not being intercepted by a man-in-the-middle (MITM)
attack.
