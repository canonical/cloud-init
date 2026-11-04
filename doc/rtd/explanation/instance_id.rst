.. _instance_id:

Instance ID
***********

The instance ID is how ``cloud-init`` tells one instance apart from another.
``Cloud-init`` uses it to decide whether the current boot is the first boot of
a new instance or a reboot of an instance it has already configured.

Where the instance ID comes from
================================

The instance ID is provided by the :ref:`datasource <datasources>`, usually
from the instance's meta-data. With :ref:`NoCloud <datasource_nocloud>`, it
is the ``instance-id`` key in the :file:`meta-data` file that you write
yourself. If no datasource is found, the
:ref:`Fallback/None <datasource_none>` datasource uses the ID
``iid-datasource-none``.

What cloud-init does with it
============================

On each boot, after a datasource is found, ``cloud-init``:

* Writes the current instance ID to :file:`/var/lib/cloud/data/instance-id`
  and to :file:`/run/cloud-init/.instance-id`.
* Writes the instance ID that was saved before this boot to
  :file:`/var/lib/cloud/data/previous-instance-id`, or
  ``NO_PREVIOUS_INSTANCE_ID`` if there was none.
* Points the :file:`/var/lib/cloud/instance` symlink at
  :file:`/var/lib/cloud/instances/<instance ID>`, where per-instance state
  (such as semaphores for modules that have already run) is kept. Any ``/``
  in the instance ID is replaced with ``_`` in this directory name.

By default, if the instance ID differs from the one saved on the previous
boot, ``cloud-init`` treats the boot as the first boot of a new instance.
Modules and scripts with a frequency of ``once-per-instance`` run again, while
those with a frequency of ``once`` do not. See
:ref:`module frequency <module_frequency>` for how to change how often a
module runs.

This means that changing the instance ID is a way to make ``cloud-init``
apply per-instance configuration again, for example after editing the
NoCloud :file:`meta-data` and :file:`user-data` files. Running
:ref:`cloud-init clean <cli_clean>` and rebooting goes further: it removes
the saved state (except the :file:`seed` directory, unless you pass
``--seed``), so modules with a frequency of ``once`` run again too.

If ``manual_cache_clean`` is set to ``true``, ``cloud-init`` does not check
the instance ID and trusts its saved state instead. In that case, changing
the instance ID has no effect; run ``cloud-init clean`` instead. For the
details of how ``cloud-init`` decides whether a boot is a first boot, see
:ref:`First_boot_determination`.

How to find the instance ID
===========================

Query the instance ID with :ref:`cloud-init query <cli_query>`:

.. code-block:: shell-session

    $ cloud-init query v1.instance_id

It is also available as ``v1.instance_id`` in
:ref:`instance data <v1_instance_id>`, so you can use it in Jinja templates in
user data as ``{{ v1.instance_id }}``.
