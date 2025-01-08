.. _First_boot_determination:

First boot determination
========================

``Cloud-init`` has to determine whether or not the current boot is the first
boot of a new instance, so that it applies the appropriate configuration. On
an instance's first boot, it should run all "per-instance" configuration,
whereas on a subsequent boot it should run only "per-boot" configuration. This
section describes how ``cloud-init`` performs this determination, as well as
why it is necessary.

When it runs, ``cloud-init`` stores a cache of its internal state for use
across stages and boots.

If this cache is present, then ``cloud-init`` has run on this system
before [#not-present]_. There are two cases where this could occur. Most
commonly, the instance has been rebooted, and this is a second/subsequent
boot. Alternatively, the filesystem has been attached to a *new* instance,
and this is the instance's first boot. The most obvious case where this
happens is when an instance is launched from an image captured from a
launched instance.

By default, ``cloud-init`` attempts to determine which case it is running
in by checking the instance ID in the cache against the instance ID it
determines at runtime. If they do not match, then this is an instance's
first boot; otherwise, it's a subsequent boot. Internally, ``cloud-init``
refers to this behaviour as ``check``.

This behaviour is required for images captured from launched instances to
behave correctly, and so is the default that generic cloud images ship with.
However, there are cases where it can cause problems [#problems]_. For these
cases, ``cloud-init`` has support for modifying its behaviour to trust the
instance ID that is present in the system unconditionally. This means that
``cloud-init`` will never detect a new instance when the cache is present,
and it follows that the only way to cause ``cloud-init`` to detect a new
instance (and therefore its first boot) is to manually remove
``cloud-init``'s cache. Internally, this behaviour is referred to as
``trust``.

To configure which of these behaviours to use, ``cloud-init`` exposes the
``manual_cache_clean`` configuration option.  When ``false`` (the default),
``cloud-init`` will ``check`` and clean the cache if the instance IDs do
not match (this is the default, as discussed above). When ``true``,
``cloud-init`` will ``trust`` the existing cache (and therefore not clean it).

Manual cache cleaning
=====================

``Cloud-init`` ships a command for manually cleaning the cache:
:command:`cloud-init clean`. See :ref:`cli_clean`'s documentation for further
details.

Reverting ``manual_cache_clean`` setting
----------------------------------------

Currently there is no support for switching an instance that is launched with
``manual_cache_clean: true`` from ``trust`` behaviour to ``check`` behaviour,
other than manually cleaning the cache.

.. warning:: If you want to capture an instance that is currently in ``trust``
   mode as an image for launching other instances, you **must** manually clean
   the cache. If you do not do so, then instances launched from the captured
   image will all detect their first boot as a subsequent boot of the captured
   instance, and will not apply any per-instance configuration.

   This is a functional issue, but also a potential security one:
   ``cloud-init`` is responsible for rotating SSH host keys on first boot,
   and this will not happen on these instances.

.. [#not-present] It follows that if this cache is not present,
   ``cloud-init`` has not run on this system before, so this is
   unambiguously this instance's first boot.

.. [#problems] A couple of ways in which this strict reliance on the presence
   of a datasource has been observed to cause problems:

    - If a cloud's instance metadata service is flaky and ``cloud-init`` cannot
      obtain the instance ID locally on that platform, ``cloud-init``'s
      instance ID determination will sometimes fail to determine the current
      instance ID, which makes it impossible to determine if this is an
      instance's first or subsequent boot (`#1885527`_).
    - If ``cloud-init`` is used to provision a physical appliance or device
      and an attacker can present a datasource to the device with a different
      instance ID, then ``cloud-init``'s default behaviour will detect this as
      an instance's first boot and reset the device using the attacker's
      configuration (this has been observed with the
      :ref:`NoCloud datasource<datasource_nocloud>` in `#1879530`_).

.. _#1885527: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/1885527
.. _#1879530: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/1879530
