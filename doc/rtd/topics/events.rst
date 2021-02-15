.. _events:

******************
Events and Updates
******************

Events
======

`Cloud-init`_ will fetch and apply cloud and user data configuration
upon serveral event types.  The two most common events for cloud-init
are when an instance first boots and any subsequent boot thereafter (reboot).
In addition to boot events, cloud-init users and vendors are interested
in when devices are added.  cloud-init currently supports the following
event types:

- **BOOT_NEW_INSTANCE**: ``New instance first boot``
- **BOOT**: ``Any system boot other than 'BOOT_NEW_INSTANCE'``

Future work will likely include infrastructure and support for the following
events:

- **HOTPLUG**: ``Dynamic add of a system device``
- **METADATA_CHANGE**: ``An instance's metadata has change``
- **USER_REQUEST**: ``Directed request to update``

Datasource Event Support
========================

All :ref:`datasources` by default support the ``BOOT_NEW_INSTANCE`` event.
Each Datasource will provide a set of events that it is capable of handling.
Datasources may not support all event types.  In some cases a system
may be configured to allow a particular event but may be running on
a platform who's datasource cannot support the event.

Configuring Event Updates
=========================

Cloud-init has a default updates policy to handle new instance
events always.  Vendors may want an instance to handle additional
events.  Users have the final say and may provide update configuration
which can be used to enable or disable handling of specific events.

updates
~~~~~~~
Specify update policy configuration for cloud-init to define which
events are allowed to be handled.  This is separate from whether a
particular platform or datasource has the capability for such events.

**policy-version**: *<Latest policy version, currently 1>*

The ``policy-version`` value specifies the updates configuration
version number.  Current version is 1, future versions may modify
the configuation structure.

**scope**:  *<name of the scope for event policy>*

The ``scope`` value is a string which defines under which domain do the
event occur.  Currently there are two known scopes: ``network`` and
``storage``.  Scopes are defined by convention but arbitrary values
can be used.

**when**: *<list of events to handle for a particular scope>*

Each ``scope`` requires a ``when`` element to specify which events
are to allowed to be handled.


Examples
========

default
~~~~~~~

The default policy for handling new instances is found in
/etc/cloud/cloud.cfg.d/10_updates_policy.cfg

.. code-block:: shell-session

 # default policy for cloud-init for when to update system config
 # such as network and storage configurations
 updates:
   policy-version: 1
   network:
     when: ['boot-new-instance']

This default policy indicates that whenever cloud-init generates a
``BOOT_NEW_INSTANCE`` event that the ``network`` scope will be updated.
This results in cloud-init applying network configuration when booting
a new instance.

.. note::
  Removing 'boot-new-instance' from the policy will cause issues when
  capturing images and booting them elsewhere as the network config
  will remain static.

apply network config every boot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
On each firsboot and every boot cloud-init will apply network configuration
found in the datasource.

.. code-block:: shell-session

 # apply network config on every boot
 updates:
   policy-version: 1
   network:
     when: ['boot-new-instance', 'boot']

.. _Cloud-init: https://launchpad.net/cloud-init
.. vi: textwidth=78
