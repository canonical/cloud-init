.. _cce-rsyslog:

Configure system logging via rsyslog
************************************

For a full list of keys, refer to the `rsyslog module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    rsyslog:
        remotes:
            maas: 192.168.1.1
            juju: 10.0.4.1
        service_reload_command: auto

Example 2
=========

.. code-block:: yaml

    #cloud-config
    rsyslog:
        config_dir: /opt/etc/rsyslog.d
        config_filename: 99-late-cloud-config.conf
        configs:
            - "*.* @@192.158.1.1"
            - content: "*.*   @@192.0.2.1:10514"
              filename: 01-example.conf
            - content: |
                *.*   @@syslogd.example.com
        remotes:
            maas: 192.168.1.1
            juju: 10.0.4.1
        service_reload_command: [your, syslog, restart, command]

Example 3
=========

Default (no) configuration with package installation on FreeBSD.

.. code-block:: yaml

    #cloud-config
    rsyslog:
        config_dir: /usr/local/etc/rsyslog.d
        check_exe: "rsyslogd"
        packages: ["rsyslogd"]
        install_rsyslog: True

.. LINKS
.. _rsyslog module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#rsyslog
