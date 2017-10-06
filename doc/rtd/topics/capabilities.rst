************
Capabilities
************

- Setting a default locale
- Setting an instance hostname
- Generating instance SSH private keys
- Adding SSH keys to a user's ``.ssh/authorized_keys`` so they can log in
- Setting up ephemeral mount points
- Configuring network devices

User configurability
====================

`Cloud-init`_ 's behavior can be configured via user-data.

    User-data can be given by the user at instance launch time.

This is done via the ``--user-data`` or ``--user-data-file`` argument to
ec2-run-instances for example.

* Check your local clients documentation for how to provide a `user-data`
  string or `user-data` file for usage by cloud-init on instance creation.


Feature detection
=================

Newer versions of cloud-init may have a list of additional features that they
support. This allows other applications to detect what features the installed
cloud-init supports without having to parse its version number. If present,
this list of features will be located at ``cloudinit.version.FEATURES``.

Currently defined feature names include:

 - ``NETWORK_CONFIG_V1`` support for v1 networking configuration,
   see :ref:`network_config_v1` documentation for examples.
 - ``NETWORK_CONFIG_V2`` support for v2 networking configuration,
   see :ref:`network_config_v2` documentation for examples.


CLI Interface :

``cloud-init features`` will print out each feature supported.  If cloud-init
does not have the features subcommand, it also does not support any features
described in this document.

.. code-block:: bash

  % cloud-init --help
  usage: cloud-init [-h] [--version] [--file FILES] [--debug] [--force]
                    {init,modules,query,single,dhclient-hook,features} ...

  optional arguments:
    -h, --help            show this help message and exit
    --version, -v         show program's version number and exit
    --file FILES, -f FILES
                          additional yaml configuration files to use
    --debug, -d           show additional pre-action logging (default: False)
    --force               force running even if no datasource is found (use at
                          your own risk)

  Subcommands:
    {init,modules,single,dhclient-hook,features,analyze,devel}
      init                initializes cloud-init and performs initial modules
      modules             activates modules using a given configuration key
      single              run a single module
      dhclient-hook       run the dhclient hookto record network info
      features            list defined features
      analyze             Devel tool: Analyze cloud-init logs and data
      devel               Run development tools

  % cloud-init features
  NETWORK_CONFIG_V1
  NETWORK_CONFIG_V2


.. _Cloud-init: https://launchpad.net/cloud-init
.. vi: textwidth=78
