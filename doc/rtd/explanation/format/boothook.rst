.. _user_data_formats-cloud_boothook:

Cloud boothook
==============

Simple Example
--------------

.. code-block:: shell

   #cloud-boothook
   #!/bin/sh
   echo 192.168.1.130 us.archive.ubuntu.com > /etc/hosts

Example of once-per-instance script
-----------------------------------

.. code-block:: bash

   #cloud-boothook
   #!/bin/sh

   # Early exit 0 when script has already run for this instance-id,
   # continue if new instance boot.
   cloud-init-per instance do-hosts /bin/false && exit 0
   echo 192.168.1.130 us.archive.ubuntu.com >> /etc/hosts

Explanation
-----------

A cloud boothook is similar to a :ref:`user-data script<user_data_script>`
in that it is a script run on boot. When run,
the environment variable ``INSTANCE_ID`` is set to the current instance ID
for use within the script.

The boothook is different in that:

* It is run very early in boot, during the :ref:`network<boot-Network>` stage,
  before any cloud-init modules are run.
* It runs every boot.

.. warning::
    Use of ``INSTANCE_ID`` variable within boothooks is deprecated.
    Use :ref:`jinja templates<user_data_formats-jinja>` with
    :ref:`v1.instance_id<v1_instance_id>` instead.

