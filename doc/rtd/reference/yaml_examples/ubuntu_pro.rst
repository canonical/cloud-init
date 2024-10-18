.. _cce-ubuntu-pro:

Configure Ubuntu Pro services
*****************************

All the examples in this page require an Ubuntu Pro contract token, which is
provided with a subscription. Pro is available for free for personal use on
up to five machines. Your subscription (and contract token) can be obtained
from: https://ubuntu.com/pro

Some services are incompatible with others and cannot be enabled at the same
time. Refer to this `compatibility matrix`_ for more details.

For a full list of keys, refer to the
:ref:`Ubuntu Pro module <mod_cc_ubuntu_pro>` schema.

Attach machine to a subscription
================================

This example attaches the machine to the subscription linked to the contract
token specified.

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example1.yaml
   :language: yaml
   :linenos:

Attach and enable FIPS and ESM
==============================

This example attaches the machine to an Ubuntu Pro subscription, also enabling
the FIPS and ESM services.

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example2.yaml
   :language: yaml
   :linenos:

Attach, enable FIPS and reboot
==============================

This example shows how to attach the machine to subscription and enable the
FIPS service, then perform a reboot after cloud-init has completed to ensure
the machine boots into the FIPS kernel.

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example3.yaml
   :language: yaml
   :linenos:

Configure a HTTP(S) proxy
=========================

This example will set a HTTP(S) proxy before attaching the machine to
subscription and enabling the FIPS service.

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example4.yaml
   :language: yaml
   :linenos:

Auto-attach but don't enable services
=====================================

Enabling services can be skipped as follows:

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example5.yaml
   :language: yaml
   :linenos:

Enable beta services
====================

This example shows how to enable both ESM and the beta real-time kernel
services. Note that real-time Ubuntu is `available on specific releases`_.

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example6.yaml
   :language: yaml
   :linenos:

Note that a reboot will be required after the real-time kernel has been
installed.

Disable auto-attach
===================

.. literalinclude:: ../../../module-docs/cc_ubuntu_pro/example7.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _compatibility matrix: https://canonical-ubuntu-pro-client.readthedocs-hosted.com/en/latest/references/compatibility_matrix/
.. _available on specific releases: https://documentation.ubuntu.com/real-time/en/latest/reference/releases/
