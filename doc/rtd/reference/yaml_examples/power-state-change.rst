.. _cce-power-state-change:

Change power state
******************

These examples demonstrate how to configure the shutdown/reboot of the system
after all other config modules have been run.

For a full list of keys, refer to the `power state change module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    power_state:
        delay: now
        mode: poweroff
        message: Powering off
        timeout: 2
        condition: true

Example 2
=========

.. code-block:: yaml

    #cloud-config
    power_state:
        delay: 30
        mode: reboot
        message: Rebooting machine
        condition: test -f /var/tmp/reboot_me

.. LINKS
.. _power state change module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#power-state-change
