.. _cce-ubunto-pro:

Configure Ubuntu Pro services
*****************************

All the examples in this page require an Ubuntu Pro contract token, which is
provided with a subscription. Pro is available for free for personal use on
up to five machines. Your subscription (and contract token) can be obtained
from: https://ubuntu.com/pro

Some services are incompatible with others and cannot be enabled at the same
time. Refer to this `compatibility matrix`_ for more details.

For a full list of keys, refer to the `Ubuntu Pro module`_ schema.

Attach machine to a subscription
================================

This example attaches the machine to the subscription linked to the contract
token specified.

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      token: <ubuntu_pro_token>

Attach and enable FIPS and ESM
==============================

This example attaches the machine to an Ubuntu Pro subscription, also enabling
the FIPS and ESM services.

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      token: <ubuntu_pro_token>
      enable:
      - fips
      - esm

Attach, enable FIPS and reboot
==============================

This example shows how to attach the machine to subscription and enable the
FIPS service, then perform a reboot after cloud-init has completed to ensure
the machine boots into the FIPS kernel.

.. code-block:: yaml

    #cloud-config
    power_state:
      mode: reboot
    ubuntu_pro:
      token: <ubuntu_pro_token>
      enable:
      - fips

Configure a http(s) proxy
=========================

This example will set a http(s) proxy before attaching the machine to
subscription and enabling the FIPS service.

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      token: <ubuntu_pro_token>
      config:
        http_proxy: 'http://some-proxy:8088'
        https_proxy: 'https://some-proxy:8088'
        global_apt_https_proxy: 'https://some-global-apt-proxy:8088/'
        global_apt_http_proxy: 'http://some-global-apt-proxy:8088/'
        ua_apt_http_proxy: 'http://10.0.10.10:3128'
        ua_apt_https_proxy: 'https://10.0.10.10:3128'
      enable:
      - fips

Auto-attach but don't enable services
=====================================

Enabling services can be skipped as follows:

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      enable: []
      enable_beta: []

Enable beta services
====================

This example shows how to enable both ESM and the beta real-time kernel
services. Note that the real-time kernel is (currently) only available on
Ubuntu 22.04 LTS (Jammy).

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      enable:
      - esm
      enable_beta:
      - realtime-kernel

Note that a reboot will be required after the real-time kernel has been
installed.

Disable auto-attach
===================

.. code-block:: yaml

    #cloud-config
    ubuntu_pro:
      features:
        disable_auto_attach: True

.. LINKS
.. _Ubuntu Pro module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ubuntu-pro
.. _compatibility matrix: https://canonical-ubuntu-pro-client.readthedocs-hosted.com/en/latest/references/compatibility_matrix/
