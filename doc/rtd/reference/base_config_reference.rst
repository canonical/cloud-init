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

    + ``cloud_dir``: Defaults to :file:`/var/lib/cloud`.
    + ``templates_dir``: Defaults to :file:`/etc/cloud/templates`.

  - ``distro``: Name of distro being used.
  - ``default_user``: Defines the default user for the system using the same
    user configuration as :ref:`Users and Groups<mod-users_groups>`. Note that
    this CAN be overridden if a ``users`` configuration
    is specified without a ``- default`` entry.
  - ``ntp_client``: The default NTP client for the distro. Takes the same
    form as ``ntp_client`` defined in :ref:`NTP<mod-ntp>`.
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

Prioritised list of datasources that ``cloud-init`` will attempt to find on
boot. By default, this will be defined in :file:`/etc/cloud/cloud.cfg.d`. There
are two primary use cases for modifying the ``datasource_list``:

1. Remove known invalid datasources. This may avoid long timeouts when
   attempting to detect datasources on any system without a systemd-generator
   hook that invokes ``ds-identify``.
2. Override default datasource ordering to discover a different datasource
   type than would typically be prioritised.

If ``datasource_list`` has only a single entry (or a single entry + ``None``),
`cloud-init` will automatically assume and use this datasource without
attempting detection.

``vendor_data``/``vendor_data2``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Allows the user to disable ``vendor_data`` or ``vendor_data2`` along with
providing a prefix for any executed scripts.

Format is a dict with ``enabled`` and ``prefix`` keys:

* ``enabled``: A boolean indicating whether to enable or disable the
  ``vendor_data``.
* ``prefix``: A path to prepend to any ``vendor_data``-provided script.

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
    - migrator
    - seed_random
    - bootcmd
    - write-files
    - growpart
    - resizefs
    - disk_setup
    - mounts
    - set_hostname
    - update_hostname
    - update_etc_hosts
    - ca-certs
    - rsyslog
    - users-groups
    - ssh

    # The modules that run in the 'config' stage
    cloud_config_modules:
    - snap
    - ssh-import-id
    - keyboard
    - locale
    - set-passwords
    - grub-dpkg
    - apt-pipelining
    - apt-configure
    - ubuntu-advantage
    - ntp
    - timezone
    - disable-ec2-metadata
    - runcmd
    - byobu

    # The modules that run in the 'final' stage
    cloud_final_modules:
    - package-update-upgrade-install
    - fan
    - landscape
    - lxd
    - ubuntu-drivers
    - write-files-deferred
    - puppet
    - chef
    - mcollective
    - salt-minion
    - reset_rmc
    - refresh_rmc_and_interface
    - rightscale_userdata
    - scripts-vendor
    - scripts-per-once
    - scripts-per-boot
    - scripts-per-instance
    - scripts-user
    - ssh-authkey-fingerprints
    - keys-to-console
    - install-hotplug
    - phone-home
    - final-message
    - power-state-change

    # System and/or distro specific settings
    # (not accessible to handlers/transforms)
    system_info:
      # This will affect which distro class gets used
      distro: ubuntu
      # Default user name + that default users groups (if added/used)
      default_user:
        name: ubuntu
        lock_passwd: True
        gecos: Ubuntu
        groups: [adm, audio, cdrom, dialout, dip, floppy, lxd, netdev, plugdev, sudo, video]
        sudo: ["ALL=(ALL) NOPASSWD:ALL"]
        shell: /bin/bash
      network:
        renderers: ['netplan', 'eni', 'sysconfig']
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


.. _configuration is templated: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
.. _cc_final_message.py: https://github.com/canonical/cloud-init/blob/main/cloudinit/config/cc_final_message.py
.. _fileConfig: https://docs.python.org/3/library/logging.config.html#logging-config-fileformat
