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

For Ubuntu systems, see also the Default Users on Ubuntu section at the end
of this page.

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

More complex examples
=====================

The following two examples are largely similar. In both we:

- Skip creation of the ``default`` user and only create ``newsuper``.
- Reject password-based login.
- Allow GitHub user ``TheRealFalcon`` and Launchpad user ``falcojr`` to SSH as
  ``newsuper``.

Set the default shell
---------------------

The default shell for ``newsuper`` is bash instead of the system default.

.. literalinclude:: ../../../module-docs/cc_users_groups/example3.yaml
   :language: yaml
   :linenos:

Configure doas/opendoas
-----------------------

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
      sudo: ALL=(ALL) NOPASSWD:ALL
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
      sudo: false
      shell: /bin/bash
      ssh_authorized_keys:
        - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDSL7uWGj8cgWsp... csmith@fringe
    - snapuser: joe@joeuser.io
    - name: nosshlogins
      ssh_redirect_user: true

Values explained
----------------

* ``name``: The user's login name.
* ``expiredate``: Date on which the user's account will be disabled.
* ``gecos``: The user name's real name, i.e. "Bob B. Smith".
* ``homedir``: (optional) Set to the local path you want to use. Defaults to
  ``/home/<username>``.
* ``primary_group``: Define the primary group. Defaults to a new group named
  after the user.
* ``groups``: (optional) Additional groups to add the user to. Defaults to
  ``None``.
* ``selinux_user``: (optional) The SELinux user for the user's login, such as
  ``"staff_u"``. When this is omitted, the system will select the default
  SELinux user.
* ``lock_passwd``: Defaults to ``true``. Lock the password to disable password
  login.
* ``inactive``: Number of days after the password expires until the account is
  disabled.
* ``passwd``: The hash -- not the password itself -- of the password you want
  to use for this user. You can generate a hash via:
  ``mkpasswd --method=SHA-512 --rounds=4096``
  (this command creates an SHA-512 password hash from stdin with 4096 salt
  rounds).

  Note: while the use of a hashed password is better than plain text, the use
  of this feature is not ideal. Also, using a high number of salting rounds
  will help, but it should not be relied upon.

  To highlight this risk, running John the Ripper against the example hash
  above, with a readily available wordlist, revealed the true password in 12
  seconds on an I7-2620QM.

  In other words, this feature is a potential security risk and is provided for
  convenience only. If you do not fully trust the medium over which your
  cloud-config will be transmitted, then you should not use this feature.

* ``no_create_home``: When set to ``true``, do not create home directory.
* ``no_user_group``: When set to ``true``, do not create a group named after
  the user.
* ``no_log_init``: When set to ``true``, do not initialize ``lastlog`` and
  ``faillog`` database.
* ``ssh_import_id``: (optional) Import SSH IDs.
* ``ssh_authorized_keys``: (optional) [list] Add keys to user's authorized keys
  file. An error is raised if ``no_create_home`` or ``system`` is also set.
* ``ssh_redirect_user``: (optional) [bool] Set ``true`` to block SSH logins for
  cloud SSH public keys and emit a message redirecting logins to use
  ``<default_username>`` instead. This option only disables cloud-provided
  public keys. An error will be raised if ``ssh_authorized_keys`` or
  ``ssh_import_id`` is provided for the same user.

* ``sudo``: Defaults to ``none``. Accepts a ``sudo`` rule string, a list of
  ``sudo`` rule strings or ``False`` to explicitly deny ``sudo`` use. Examples:

  * Allow a user unrestricted sudo access: ::

       sudo:  ALL=(ALL) NOPASSWD:ALL

  * Adding multiple sudo rule strings: ::

       sudo:
         - ALL=(ALL) NOPASSWD:/bin/mysql``
         - ALL=(ALL) ALL

  * Prevent sudo access for a user: ::

       sudo: False

  Note: Double check your syntax and make sure it is valid. Cloud-init does not
  parse/check the syntax of the ``sudo`` directive.

* ``system``: Create the user as a system user. This means no home directory.
* ``snapuser``: Create a Snappy (Ubuntu-Core) user via the ``snap create-user``
  command available on Ubuntu systems. If the user has an account on the Ubuntu
  SSO, specifying the email will allow snap to request a username and any
  public SSH keys, and will import these into the system with the username
  specified by their SSO account.

  If the username is not set in SSO, then ``username`` will be the shortname
  before the email domain.

Default users on Ubuntu
-----------------------

Unless you define users, you will get an ``'ubuntu'`` user on Ubuntu systems
with the legacy permission (no password ``sudo``, locked user, etc). If,
however, you want to have the ``'ubuntu'`` user in addition to other users,
you need to instruct cloud-init that you **also** want the default user. To do
this, use the following syntax:

.. code-block:: yaml

   users:
     - default
     - bob
     - ....
   foobar: ...

* ``users[0]`` (the first user in users) overrides the ``user`` directive.
* The ``'default'`` user above references the distro's config set in
  ``/etc/cloud/cloud.cfg``.

