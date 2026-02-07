.. _user_data_script:

User-data script
================

Example
-------

.. code-block:: shell

    #!/bin/sh
    echo "Hello World" > /var/tmp/output.txt

Explanation
-----------

A user-data script is a single script to be executed once per instance.
User-data scripts are run relatively late in the boot process, during
cloud-init's :ref:`final stage<boot-Final>` as part of the
:ref:`cc_scripts_user<mod_cc_scripts_user>` module.

.. warning::
    Use of ``INSTANCE_ID`` variable within user-data scripts is deprecated.
    Use :ref:`jinja templates<user_data_formats-jinja>` with
    :ref:`v1.instance_id<v1_instance_id>` instead.
