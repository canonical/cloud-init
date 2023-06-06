.. _events:

Events and updates
******************

Events
======

``Cloud-init`` will fetch and apply cloud and user data configuration
upon several event types. The two most common events for ``cloud-init``
are when an instance first boots and any subsequent boot thereafter (reboot).
In addition to boot events, ``cloud-init`` users and vendors are interested
in when devices are added. ``Cloud-init`` currently supports the following
event types:

- ``BOOT_NEW_INSTANCE``: New instance first boot.
- ``BOOT``: Any system boot other than ``BOOT_NEW_INSTANCE``.
- ``BOOT_LEGACY``: Similar to ``BOOT``, but applies networking config twice
  each boot: once during the :ref:`Local stage<boot-Local>`, then again in the
  :ref:`Network stage<boot-Network>`. As this behaviour was previously the
  default behaviour, this option exists to prevent regressing such behaviour.
- ``HOTPLUG``: Dynamic add of a system device.

Future work will likely include infrastructure and support for the following
events:

- ``METADATA_CHANGE``: An instance's metadata has changed.
- ``USER_REQUEST``: Directed request to update.

Datasource event support
========================

All :ref:`datasources<datasources>` support the ``BOOT_NEW_INSTANCE`` event
by default. Each datasource will declare a set of these events that it is
capable of handling. Datasources may not support all event types. In some
cases a system may be configured to allow a particular event but may be
running on a platform whose datasource cannot support the event.

Configuring event updates
=========================

Update configuration may be specified via user data, which can be used to
enable or disable handling of specific events. This configuration will be
honored as long as the events are supported by the datasource. However,
configuration will always be applied at first boot, regardless of the user
data specified.

Updates
-------

Update policy configuration defines which events are allowed to be handled.
This is separate from whether a particular platform or datasource has the
capability for such events.

``scope``: *<name of the* ``scope`` *for event policy>*
  The ``scope`` value is a string which defines which domain the event occurs
  under. Currently, the only known ``scope`` is ``network``, though more
  ``scopes`` may be added in the future. ``Scopes`` are defined by convention
  but arbitrary values can be used.

``when``: *<list of events to handle for a particular* ``scope`` *>*
  Each ``scope`` requires a ``when`` element to specify which events
  are to allowed to be handled.

Hotplug
=======

When the ``hotplug`` event is supported by the datasource and configured in
user data, ``cloud-init`` will respond to the addition or removal of network
interfaces to the system. In addition to fetching and updating the system
metadata, ``cloud-init`` will also bring up/down the newly added interface.

.. warning::
   Due to its use of ``systemd`` sockets, ``hotplug`` functionality is
   currently incompatible with SELinux. This issue is being `tracked
   in GitHub #3890`_. Additionally, ``hotplug`` support is considered
   experimental for non-Debian-based systems.

Example
=======

Apply network config every boot
-------------------------------

On every boot, apply network configuration found in the datasource.

.. code-block:: shell-session

   # apply network config on every boot
   updates:
     network:
       when: ['boot']

.. _Cloud-init: https://launchpad.net/cloud-init
.. _tracked in Github #3890: https://github.com/canonical/cloud-init/issues/3890
