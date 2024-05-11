.. _cce-ntp:

Network Time Protocol (NTP)
***************************

The NTP module configures NTP services. If NTP is not installed on the system,
but NTP configuration is specified, NTP will be installed.

For a full list of keys, refer to the `NTP module`_ schema.

Example 1
=========

- ``servers``:
  List of NTP servers to sync with.
- ``pools``:
  List of NTP pool servers to sync with. Pools are typically DNS hostnames
  which resolve to different specific servers to load balance a set of
  services.

Each server in the list will be added in list-order in the format:

.. code-block:: yaml

   [pool|server] <server entry> iburst

If no servers or pools are defined but NTP is enabled, then cloud-init will
render the distro default list of pools:

.. code-block:: yaml

    pools = [
       '0.{distro}.pool.ntp.org',
       '1.{distro}.pool.ntp.org',
       '2.{distro}.pool.ntp.org',
       '3.{distro}.pool.ntp.org',
    ]

So putting these together, we can see a straightforward example:

.. code-block:: yaml

    #cloud-config
    ntp:
      pools: ['0.company.pool.ntp.org', '1.company.pool.ntp.org', 'ntp.myorg.org']
      servers: ['my.ntp.server.local', 'ntp.ubuntu.com', '192.168.23.2']

Example 2
=========

Here we override NTP with chrony configuration on Ubuntu. The example uses
cloud-init default chrony configuration.

.. code-block:: yaml

    #cloud-config
    ntp:
      enabled: true
      ntp_client: chrony

Example 3
=========

This example provides a custom NTP client configuration.

.. code-block:: yaml

    #cloud-config
    ntp:
      enabled: true
      ntp_client: myntpclient
      config:
         confpath: /etc/myntpclient/myntpclient.conf
         check_exe: myntpclientd
         packages:
           - myntpclient
         service_name: myntpclient
         template: |
             ## template:jinja
             # My NTP Client config
             {% if pools -%}# pools{% endif %}
             {% for pool in pools -%}
             pool {{pool}} iburst
             {% endfor %}
             {%- if servers %}# servers
             {% endif %}
             {% for server in servers -%}
             server {{server}} iburst
             {% endfor %}
             {% if peers -%}# peers{% endif %}
             {% for peer in peers -%}
             peer {{peer}}
             {% endfor %}
             {% if allow -%}# allow{% endif %}
             {% for cidr in allow -%}
             allow {{cidr}}
             {% endfor %}
      pools: [0.int.pool.ntp.org, 1.int.pool.ntp.org, ntp.myorg.org]
      servers:
        - ntp.server.local
        - ntp.ubuntu.com
        - 192.168.23.2
      allow:
        - 192.168.23.0/32
      peers:
        - km001
        - km002

.. LINKS
.. _NTP module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ntp
