.. _cce-user-groups:

Configure users and groups
**************************

These examples will show how you can configure users and groups.

For a full list of keys, and more details of how to use this module, refer to
the :ref:`users and groups module <mod_cc_users_groups>` schema.

Add default user
================

.. literalinclude:: ../../../module-docs/cc_users_groups/example1.yaml
   :language: yaml
   :linenos:

Don't create any default user
=============================

.. literalinclude:: ../../../module-docs/cc_users_groups/example8.yaml
   :language: yaml
   :linenos:

Add groups to the system
========================

The following example adds the ``'admingroup'`` group, with members ``'root'``
and ``'sys'``, and the empty group ``cloud-users``.

.. literalinclude:: ../../../module-docs/cc_users_groups/example2.yaml
   :language: yaml
   :linenos:

Add users to the system
=======================

Users are added after groups. Note that most of these configuration options
will not be honored if the user already exists. The following options are
exceptions and can be applied to already-existing users:

- ``plain_text_passwd``
- ``hashed_passwd``
- ``lock_passwd``
- ``sudo``
- ``ssh_authorized_keys``
- ``ssh_redirect_user``

.. code-block:: yaml

    #cloud-config
    users:
    - default
    - name: foobar
      gecos: Foo B. Bar
      primary_group: foobar
      groups: users
      selinux_user: staff_u
      expiredate: '2032-09-01'
      ssh_import_id:
        - lp:falcojr
        - gh:TheRealFalcon
      lock_passwd: false
      passwd: $6$j212wezy$7H/1LT4f9/N3wpgNunhsIqtMj62OKiS3nyNwuizouQc3u7MbYCarYeAHWYPYb2FT.lbioDm2RrkJPb9BZMN1O/
    - name: barfoo
      gecos: Bar B. Foo
      sudo: "ALL=(ALL) NOPASSWD:ALL"
      groups: users, admin
      ssh_import_id:
        - lp:falcojr
        - gh:TheRealFalcon
      lock_passwd: true
      ssh_authorized_keys:
        - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDSL7uWGj8cgWsp... csmith@fringe
    - name: cloudy
      gecos: Magic Cloud App Daemon User
      inactive: '5'
      system: true
    - name: fizzbuzz
      shell: /bin/bash
      ssh_authorized_keys:
        - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDSL7uWGj8cgWsp... csmith@fringe
    - snapuser: joe@joeuser.io
    - name: nosshlogins
      ssh_redirect_user: true

Set the default shell
=====================

The default shell for ``newsuper`` is bash instead of the system default.

.. literalinclude:: ../../../module-docs/cc_users_groups/example3.yaml
   :language: yaml
   :linenos:

Configure doas/opendoas
=======================

Here we configure ``doas``/``opendoas`` to permit this user to run commands as
other users without being prompted for a password (except not as root).

.. literalinclude:: ../../../module-docs/cc_users_groups/example4.yaml
   :language: yaml
   :linenos:

On SELinux
==========

On a system with SELinux enabled, this example will add ``youruser`` and set
the SELinux user to ``staff_u``. When omitted on SELinux, the system will
select the configured default SELinux user.

.. literalinclude:: ../../../module-docs/cc_users_groups/example5.yaml
   :language: yaml
   :linenos:

Redirect legacy username
========================

To redirect a legacy username to the default user for a distribution,
``ssh_redirect_user`` will accept an SSH connection and show a message telling
the client to SSH as the default user. SSH clients will get the message:

.. literalinclude:: ../../../module-docs/cc_users_groups/example6.yaml
   :language: yaml
   :linenos:

Override default user config
============================

Override any ``default_user`` config in ``/etc/cloud/cloud.cfg`` with
supplemental config options. This config will make the default user
``mynewdefault`` and change the user to not have ``sudo`` rights.

.. literalinclude:: ../../../module-docs/cc_users_groups/example7.yaml
   :language: yaml
   :linenos:
