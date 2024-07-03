.. _base_config_reference:

Base configuration
******************

.. warning::
    This documentation is intended for custom image creators, such as distros
    and cloud providers, not end users. Modifying the base configuration
    should not be necessary for end users and can result in a system that may
    be unreachable or may no longer boot.

``Cloud-init`` base config is primarily defined in two places:

* :file:`/etc/cloud/cloud.cfg`
* :file:`/etc/cloud/cloud.cfg.d/*.cfg`

See the :ref:`configuration sources explanation<configuration>` for more
information on how these files get sourced and combined with other
configuration.

Generation
==========

:file:`cloud.cfg` isn't present in any of ``cloud-init``'s source files. The
`configuration is templated`_ and customised for each
distribution supported by ``cloud-init``.

Base configuration keys
=======================

Module keys
-----------

Modules are grouped into the following keys:

* ``cloud_init_modules``: Modules run during :ref:`network<boot-Network>`
  timeframe.
* ``cloud_config_modules``: Modules run during :ref:`config<boot-Config>`
  timeframe.
* ``cloud_final_modules``: Modules run during :ref:`final<boot-Final>`
  timeframe.

Each ``module`` definition contains an array of strings, where each string
is the name of the module. Each name is taken directly from the module
filename, with the ``cc_`` prefix and ``.py`` suffix removed, and with ``-``
and ``_`` being interchangeable.

Alternatively, in place of the module name, an array of
``<name>, <frequency>[, <args>]`` args may be specified. See
:ref:`the module creation guidelines<module_creation-Guidelines>` for
more information on ``frequency`` and ``args``.

.. note::
    Most modules won't run at all if they're not triggered via a
    respective user data key, so removing modules or changing the run
    frequency is **not** a recommended way to reduce instance boot time.

Examples
--------

To specify that only `cc_final_message.py`_ run during final timeframe:

.. code-block:: yaml

    cloud_final_modules:
    - final_message

To change the frequency from the default of ``ALWAYS`` to ``ONCE``:

.. code-block:: yaml

    cloud_final_modules:
    - [final_message, once]

To include default arguments to the module (that may be overridden by
user data):

.. code-block:: yaml

    cloud_final_modules:
    - [final_message, once, "my final message"]

.. _base_config-Datasource:

Datasource keys
---------------

Many datasources allow configuration of the datasource for use in
querying the datasource for metadata using the ``datasource`` key.
This configuration is datasource dependent and can be found under
each datasource's respective :ref:`documentation<datasources>`. It will
generally take the form of:

.. code-block:: yaml

    datasource:
      <datasource_name>:
        ...

System info keys
----------------

These keys are used for setup of ``cloud-init`` itself, or the datasource
or distro. Anything under ``system_info`` cannot be overridden by vendor data,
user data, or any other handlers or transforms. In some cases there may be a
``system_info`` key used for the distro, while the same key is used outside of
``system_info`` for a user data module.
Both keys will be processed independently.

* ``system_info``: Top-level key.

  - ``paths``: Definitions of common paths used by ``cloud-init``.

    + ``cloud_dir``: Default: :file:`/var/lib/cloud`.
    + ``templates_dir``: Default: :file:`/etc/cloud/templates`.

  - ``distro``: Name of distro being used.
  - ``default_user``: Defines the default user for the system using the same
    user configuration as :ref:`Users and Groups<mod_cc_users_groups>`. Note
    that this CAN be overridden if a ``users`` configuration
    is specified without a ``- default`` entry.
  - ``ntp_client``: The default NTP client for the distro. Takes the same
    form as ``ntp_client`` defined in :ref:`NTP<mod_cc_ntp>`.
  - ``package_mirrors``: Defines the package mirror info for apt.
  - ``ssh_svcname``: The SSH service name. For most distros this will be
    either ``ssh`` or ``sshd``.
  - ``network``: Top-level key for distro-specific networking configuration.

    + ``renderers``: Prioritised list of networking configurations to try
      on this system. The first valid entry found will be used.
      Options are:

      * ``eni``: For :file:`/etc/network/interfaces`.
      * ``network-manager``
      * ``netplan``
      * ``networkd``: For ``systemd-networkd``.
      * ``freebsd``
      * ``netbsd``
      * ``openbsd``

    + ``activators``: Prioritised list of networking tools to try to activate
      network on this system. The first valid entry found will be used.
      Options are:

      * ``eni``: For ``ifup``/``ifdown``.
      * ``netplan``: For ``netplan generate``/``netplan apply``.
      * ``network-manager``: For ``nmcli connection load``/
        ``nmcli connection up``.
      * ``networkd``: For ``ip link set up``/``ip link set down``.
  - ``apt_get_command``: Command used to interact with APT repositories.
    Default: ``apt-get``.
  - ``apt_get_upgrade_subcommand``: APT subcommand used to upgrade system.
    Default: ``dist-upgrade``.
  - ``apt_get_wrapper``: Command used to wrap the apt-get command.

    + ``enabled``: Whether to use the specified ``apt_wrapper`` command.
      If set to ``auto``, use the command if it exists on the ``PATH``.
      Default: ``true``.

    + ``command``: Command used to wrap any ``apt-get`` calls.
      Default: ``eatmydata``.

Logging keys
------------

See :ref:`the logging explanation<logging>` for a comprehensive
logging explanation. Note that ``cloud-init`` has a default logging
definition that shouldn't need to be altered. It is defined in this
instance at :file:`/etc/cloud/cloud.cfg.d/05_logging.cfg`.

The logging keys used in the base configuration are as follows:

``logcfg``
^^^^^^^^^^

A standard python `fileConfig`_ formatted log configuration.
This is the primary logging configuration key and will take precedence over
``log_cfgs`` or ``log_basic`` keys.

``log_cfgs``
^^^^^^^^^^^^

A list of logging configs in `fileConfig`_ format to apply
when running ``cloud-init``. Note that ``log_cfgs`` is used in
:file:`/etc/cloud.cfg.d/05_logging.cfg`.

``log_basic``
^^^^^^^^^^^^^

Boolean value to determine if ``cloud-init`` should apply a
basic default logging configuration if none has been provided. Defaults
to ``true`` but only takes effect if ``logcfg`` or ``log_cfgs`` hasn't
been defined.

``output``
^^^^^^^^^^

If and how to redirect ``stdout``/``stderr``. Defined in
:file:`/etc/cloud.cfg.d/05_logging.cfg` and explained in
:ref:`the logging explanation<logging_command_output>`.

``syslog_fix_perms``
^^^^^^^^^^^^^^^^^^^^

Takes a list of ``<owner:group>`` strings and will set the owner of
``def_log_file`` accordingly.

``def_log_file``
^^^^^^^^^^^^^^^^

Only used in conjunction with ``syslog_fix_perms``.
Specifies the filename to be used for setting permissions. Defaults
to :file:`/var/log/cloud-init.log`.

Other keys
----------

``network``
^^^^^^^^^^^

The :ref:`network configuration<network_config>` to be applied to this
instance.

``datasource_pkg_list``
^^^^^^^^^^^^^^^^^^^^^^^

Prioritised list of python packages to search when finding a datasource.
Automatically includes ``cloudinit.sources``.

.. _base_config_datasource_list:

``datasource_list``
^^^^^^^^^^^^^^^^^^^

This key contains a prioritised list of datasources that ``cloud-init``
attempts to discover on boot. By default, this is defined in
:file:`/etc/cloud/cloud.cfg.d`.

There are a few reasons to modify the ``datasource_list``:

1. Override default datasource discovery priority order
2. Force cloud-init to use a specific datasource: A single entry in
   the list (or a single entry and ``None``) will override datasource
   discovery, which will force the specified datasource to run.
3. Remove known invalid datasources: this might improve boot speed on distros
   that do not use ``ds-identify`` to detect and select the datasource,

.. warning::

   This key is unique in that it uses a subset of YAML syntax. It **requires**
   that the key and its contents, a list, must share a single line - no
   newlines.

``vendor_data``/``vendor_data2``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Allows the user to disable ``vendor_data`` or ``vendor_data2`` along with
providing a prefix for any executed scripts.

Format is a dict with ``enabled`` and ``prefix`` keys:

* ``enabled``: A boolean indicating whether to enable or disable the
  ``vendor_data``.
* ``prefix``: A path to prepend to any ``vendor_data``-provided script.

``manual_cache_clean``
^^^^^^^^^^^^^^^^^^^^^^

By default, cloud-init searches for a datasource on every boot. Setting
this to ``true`` will disable this behaviour. This is useful if your datasource
information will not be present every boot. Default: ``false``.

Example
=======

On an Ubuntu system, :file:`/etc/cloud/cloud.cfg` should look similar to:

.. code-block:: yaml

    # The top level settings are used as module and base configuration.
    # A set of users which may be applied and/or used by various modules
    # when a 'default' entry is found it will reference the 'default_user'
    # from the distro configuration specified below
    users:
    - default


    # If this is set, 'root' will not be able to ssh in and they
    # will get a message to login instead as the default $user
    disable_root: true

    # This will cause the set+update hostname module to not operate (if true)
    preserve_hostname: false

    # If you use datasource_list array, keep array items in a single line.
    # If you use multi line array, ds-identify script won't read array items.
    # Example datasource config
    # datasource:
    #    Ec2:
    #      metadata_urls: [ 'blah.com' ]
    #      timeout: 5 # (defaults to 50 seconds)
    #      max_wait: 10 # (defaults to 120 seconds)

    # The modules that run in the 'init' stage
    cloud_init_modules:
    - seed_random
    - bootcmd
    - write_files
    - growpart
    - resizefs
    - disk_setup
    - mounts
    - set_hostname
    - update_hostname
    - update_etc_hosts
    - ca_certs
    - rsyslog
    - users_groups
    - ssh

    # The modules that run in the 'config' stage
    cloud_config_modules:
    - wireguard
    - snap
    - ubuntu_autoinstall
    - ssh_import_id
    - keyboard
    - locale
    - set_passwords
    - grub_dpkg
    - apt_pipelining
    - apt_configure
    - ubuntu_pro
    - ntp
    - timezone
    - disable_ec2_metadata
    - runcmd
    - byobu

    # The modules that run in the 'final' stage
    cloud_final_modules:
    - package_update_upgrade_install
    - fan
    - landscape
    - lxd
    - ubuntu_drivers
    - write_files_deferred
    - puppet
    - chef
    - ansible
    - mcollective
    - salt_minion
    - reset_rmc
    - scripts_vendor
    - scripts_per_once
    - scripts_per_boot
    - scripts_per_instance
    - scripts_user
    - ssh_authkey_fingerprints
    - keys_to_console
    - install_hotplug
    - phone_home
    - final_message
    - power_state_change

    # System and/or distro specific settings
    # (not accessible to handlers/transforms)
    system_info:
      # This will affect which distro class gets used
      distro: ubuntu
      # Default user name + that default users groups (if added/used)
      default_user:
        name: ubuntu
        doas:
          - permit nopass ubuntu
        lock_passwd: True
        gecos: Ubuntu
        groups: [adm, cdrom, dip, lxd, sudo]
        sudo: ["ALL=(ALL) NOPASSWD:ALL"]
        shell: /bin/bash
      network:
        dhcp_client_priority: [dhclient, dhcpcd, udhcpc]
        renderers: ['netplan', 'eni', 'sysconfig']
        activators: ['netplan', 'eni', 'network-manager', 'networkd']
      # Automatically discover the best ntp_client
      ntp_client: auto
      # Other config here will be given to the distro class and/or path classes
      paths:
        cloud_dir: /var/lib/cloud/
        templates_dir: /etc/cloud/templates/
      package_mirrors:
        - arches: [i386, amd64]
        failsafe:
            primary: http://archive.ubuntu.com/ubuntu
            security: http://security.ubuntu.com/ubuntu
        search:
            primary:
            - http://%(ec2_region)s.ec2.archive.ubuntu.com/ubuntu/
            - http://%(availability_zone)s.clouds.archive.ubuntu.com/ubuntu/
            - http://%(region)s.clouds.archive.ubuntu.com/ubuntu/
            security: []
        - arches: [arm64, armel, armhf]
        failsafe:
            primary: http://ports.ubuntu.com/ubuntu-ports
            security: http://ports.ubuntu.com/ubuntu-ports
        search:
            primary:
            - http://%(ec2_region)s.ec2.ports.ubuntu.com/ubuntu-ports/
            - http://%(availability_zone)s.clouds.ports.ubuntu.com/ubuntu-ports/
            - http://%(region)s.clouds.ports.ubuntu.com/ubuntu-ports/
            security: []
        - arches: [default]
        failsafe:
            primary: http://ports.ubuntu.com/ubuntu-ports
            security: http://ports.ubuntu.com/ubuntu-ports
      ssh_svcname: ssh

    # configure where output will go
    output:
      init: "> /var/log/my-cloud-init.log"
      config: [ ">> /tmp/foo.out", "> /tmp/foo.err" ]
      final:
        output: "| tee /tmp/final.stdout | tee /tmp/bar.stdout"
        error: "&1"

    # Set `true` to enable the stop searching for a datasource on boot.
    manual_cache_clean: False

    # def_log_file and syslog_fix_perms work together
    # if
    # - logging is set to go to a log file 'L' both with and without syslog
    # - and 'L' does not exist
    # - and syslog is configured to write to 'L'
    # then 'L' will be initially created with root:root ownership (during
    # cloud-init), and then at cloud-config time (when syslog is available)
    # the syslog daemon will be unable to write to the file.
    #
    # to remedy this situation, 'def_log_file' can be set to a filename
    # and syslog_fix_perms to a string containing "<user>:<group>"
    def_log_file: /var/log/my-logging-file.log
    syslog_fix_perms: syslog:root



.. _configuration is templated: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
.. _cc_final_message.py: https://github.com/canonical/cloud-init/blob/main/cloudinit/config/cc_final_message.py
.. _fileConfig: https://docs.python.org/3/library/logging.config.html#logging-config-fileformat
