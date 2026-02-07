.. _user_data_formats-jinja:

Jinja template
==============

.. _jinja-config:

Example cloud-config
--------------------

.. code-block:: yaml

   ## template: jinja
   #cloud-config
   runcmd:
     - echo 'Running on {{ v1.cloud_name }}' > /var/tmp/cloud_name

.. _jinja-script:

Example user-data script
------------------------

.. code-block:: shell

   ## template: jinja
   #!/bin/sh
   echo 'Current instance id: {{ v1.instance_id }}' > /var/tmp/instance_id

Explanation
-----------

`Jinja templates <https://jinja.palletsprojects.com/>`_ may be used for
cloud-config and user-data scripts. Any
:ref:`instance-data variables<instance-data-keys>` may be used
as jinja template variables. Any jinja templated configuration must contain
the original header along with the new jinja header above it.

.. note::
    Use of Jinja templates is supported for cloud-config, user-data
    scripts, and cloud-boothooks. Jinja templates are not supported for
    meta configs.

