.. _datasource_wsl:

WSL
***

The Windows Subsystem for Linux (WSL) somewhat resembles a container
hypervisor. A Windows user may have as many Linux distro instances as they
wish, either created by the distro-launcher workflow (for the distros delivered
through MS Store) or by importing a tarball containing a root filesystem. This
page assumes the reader is familiar with WSL. To learn more about that, please
visit the `Microsoft documentation <https://learn.microsoft.com/windows/wsl/about>`_.

Requirements
==============

1. **WSL interoperability must be enabled**. The datasource needs to execute
   some Windows binaries to compute the possible locations of the user data
   files.

2. **WSL automount must be enabled**. The datasource needs to access files in
   the Windows host filesystem.

3. **The init system must be aware of cloud-init**. WSL has opt-in support for
   systemd, thus for distros that rely on it, such as Ubuntu, cloud-init will
   run automatically if systemd is enabled via the ``/etc/wsl.conf``. The
   Ubuntu applications distributed via Microsoft Store enable systemd in the
   first boot, so no action is required if the user sets up a new instance by
   using them. Users of other distros may find it surprising that cloud-init
   doesn't run automatically by default. At the time of this writing, only
   systemd distros are supported by the WSL datasource, although there is
   nothing hard-coded in the implementation code that requires it, so
   non-systemd distros may find ways to run cloud-init and make it just work.

Notice that requirements 1 and 2 are met by default, i.e. WSL grants those
features enabled. Users can disable those features, though. That would prevent
the datasource from working.
For more information about how to configure WSL,
`check the official documentation <https://learn.microsoft.com/windows/wsl/wsl-config#configuration-settings-for-wslconf>`_.

.. _wsl_user_data_configuration:

User data configuration
========================

The WSL datasource relies exclusively on the Windows filesystem as the provider
of user data. Access to those files is provided by WSL itself unless disabled
by the user, thus the datasource doesn't require any special component running
on the Windows host to provide such data.

User data can be supplied in any
:ref:`format supported by cloud-init<user_data_formats>`, such as YAML
cloud-config files or shell scripts. At runtime, the WSL datasource looks for
user data in the following locations inside the Windows host filesystem, in the
order specified below.

First, configurations from Ubuntu Pro/Landscape are checked for in the
following paths:

1. ``%USERPROFILE%\.ubuntupro\.cloud-init\<InstanceName>.user-data`` holds data
   provided by Landscape to configure a specific WSL instance. If this file
   is present, normal user-provided configurations are not looked for. This
   file is merged with (2) on a per-module basis. If this file is not present,
   then the first user-provided configuration will be used in its place.

2. ``%USERPROFILE%\.ubuntupro\.cloud-init\agent.yaml`` holds data provided by
   the Ubuntu Pro for WSL agent. If this file is present, its modules will be
   merged with (1), overriding any conflicting modules. If (1) is not provided,
   then this file will be merged with any valid user-provided configuration
   instead.

Then, if a file from (1) is not found, a user-provided configuration will be
looked for instead in the following order:

1. ``%USERPROFILE%\.cloud-init\<InstanceName>.user-data`` holds user data for a
   specific instance configuration. The datasource resolves the name attributed
   by WSL to the instance being initialized and looks for this file before any
   of the subsequent alternatives. Example: ``sid-mlkit.user-data`` matches an
   instance named ``Sid-MLKit``.

2. ``%USERPROFILE%\.cloud-init\<ID>-<VERSION_ID>.user-data`` for the
   distro-specific configuration, matched by the distro ID and VERSION_ID
   entries as specified in ``/etc/os-release``.  If VERSION_ID is not present,
   then VERSION_CODENAME will be used instead.
   Example:
   ``ubuntu-22.04.user-data`` will affect any instance created from an Ubuntu
   22.04 Jammy Jellyfish image if a more specific configuration file does not
   match.

3. ``%USERPROFILE%\.cloud-init\<ID>-all.user-data`` for the distro-specific
   configuration, matched by the distro ID entry in ``/etc/os-release``,
   regardless of the release version. Example: ``debian-all.user-data`` will
   affect any instance created from any Debian GNU/Linux image, regardless of
   which release, if a more specific configuration file does not match.

4. ``%USERPROFILE%\.cloud-init\default.user-data`` for the configuration
   affecting all instances, regardless of which distro and release version, if
   a more specific configuration file does not match. That could be used, for
   example, to automatically create a user with the same name across all WSL
   instances a user may have.

Only the first match is loaded, and no config merging is done, even in the
presence of errors. That avoids unexpected behaviour due to surprising merge
scenarios. Also, notice that the file name casing is irrelevant since both the
Windows file names, as well as the WSL distro names, are case-insensitive by
default. If none are found, cloud-init remains disabled if no other
configurations from previous steps were found.

.. note::
   Some users may have configured case sensitivity for file names on Windows.
   Note that user data files will still be matched case-insensitively. If there
   are both `InstanceName.user-data` and `instancename.user-data`, which one
   will be chosen is arbitrary and should not be relied on. Thus it's
   recommended to avoid that scenario to prevent confusion.

Since WSL instances are scoped by the Windows user, having the user data files
inside the ``%USERPROFILE%`` directory (typically ``C:\Users\<USERNAME>``)
ensures that WSL instance initialization won't be subject to naming conflicts
if the Windows host is shared by multiple users.


Vendor and metadata
===================

The current implementation doesn't allow supplying vendor data.
The reasoning is that vendor data adds layering, thus complexity, for no real
benefit to the user. Supplying vendor data could be relevant to WSL itself, if
the subsystem was aware of cloud-init and intended to leverage it, which is not
the case to the best of our knowledge at the time of this writing.

Most of what ``metadata`` is intended for is not applicable under WSL, such as
setting a hostname. Yet, the knowledge of ``metadata.instance-id`` is vital for
cloud-init. So, this datasource provides a default value but also supports
optionally sourcing metadata from a per-instance specific configuration file:
``%USERPROFILE%\.cloud-init\<InstanceName>.meta-data``. If that file exists, it
is a YAML-formatted file minimally providing a value for instance ID
such as: ``instance-id: x-y-z``. Advanced users looking to share
snapshots or relaunch a snapshot where cloud-init is re-triggered, must run
``sudo cloud-init clean --logs`` on the instance before snapshot/export, or
create the appropriate ``.meta-data`` file containing ``instance-id:
some-new-instance-id``.

Unsupported or restricted modules and features
===============================================

Certain features of cloud-init and its modules either require further
customization in the code to better fit the WSL platform or cannot be supported
at all due to the constraints of that platform. When writing user-data config
files, please check the following restrictions:

* File paths in an include file must be Linux absolute paths.

  Users may be surprised with that requirement since the user data files are
  inside the Windows file system. But remember that cloud-init is still running
  inside a Linux instance, and the files referenced in the include user data
  file will be read by cloud-init, thus they must be represented with paths
  understandable inside the Linux instance. Most users will find their Windows
  system drive mounted as `/mnt/c`, so let's consider that assumption in the
  following example:

``C:\Users\Me\.cloud-init\noble-cpp.user-data``

.. code-block::

   #include
   /mnt/c/Users/me/.cloud-init/config.user-data
   /mnt/c/Users/me/Downloads/cpp.yaml

When initializing an instance named ``Noble-Cpp`` cloud-init will find that
include file, referring to files inside the Windows file system, and will load
them effectively. A failure would happen if Windows paths were otherwise in the
include file.

* Network configuration is not supported.

  WSL has full control of the instances' networking features and configuration.
  A limited set of options for networking is exposed to the user via
  ``/etc/wsl.conf``. Those options don't fit well with the networking model
  cloud-init expects or understands.

* Set hostname.

  WSL automatically assigns the instance hostname and any attempt to change it
  will take effect only until the next boot when WSL takes over again.
  The user can set the desired hostname via ``/etc/wsl.conf``, if necessary.

* Default user.

  While creating users through cloud-init works as in any other platform, WSL
  has the concept of the *default user*, which is the user logged in by
  default. So, to create the default user with cloud-init, one must supply user
  data to the :ref:`Users and Groups module <mod_cc_users_groups>` and write
  the entry in ``/etc/wsl.conf`` to make that user the default. See the
  example:

.. code-block:: yaml

    #cloud-config
    users:
    - name: j
      gecos: Agent J
      groups: users,sudo,netdev,audio
      sudo: ALL=(ALL) NOPASSWD:ALL
      shell: /bin/bash
      lock_passwd: true

    write_files:
    - path: /etc/wsl.conf
      append: true
      contents: |
        [user]
        default=j

* Disk setup, Growpart, Mounts and Resizefs.

  The root filesystem must have the layout expected by WSL. Other mount points
  may work, depending on how the hardware devices are exposed by the Windows
  host, and fstab processing during boot is subject to configuration via
  ``/etc/wsl.conf``, so users should expect limited functionality.

* GRUB dpkg.

  WSL controls the boot process, meaning that attempts to install and configure
  GRUB as any other bootloader won't be effective.

* Resolv conf and update etc/ hosts.

  WSL automatically generates those files by default, unless configured to
  behave otherwise in ``/etc/wsl.conf``. Overwriting may work, but only
  until the next reboot.
