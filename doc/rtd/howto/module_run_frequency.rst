.. _module_frequency:

How to change a module's run frequency
**************************************

You may want to change the default frequency at which a module runs, for
example, to make the module run on every boot.

To override the default frequency, you will need to modify the module
list in :file:`/etc/cloud/cloud.cfg`:

1. Change the module from a string (default) to a list.
2. Set the first list item to the module name and the second item to the
   frequency.

Example
=======

The following example demonstrates how to log boot times to a file every boot.

Update :file:`/etc/cloud/cloud.cfg`:

.. code-block:: yaml
   :name: /etc/cloud/cloud.cfg
   :emphasize-lines: 3

        cloud_final_modules:
        # list shortened for brevity
         - [phone_home, always]
         - final_message
         - power_state_change

Then your user-data could then be:

.. code-block:: yaml

        ## template: jinja
        #cloud-config
        phone_home:
            url: http://example.com/{{ v1.instance_id }}/
            post: all
