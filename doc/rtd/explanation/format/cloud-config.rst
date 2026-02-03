.. _user_data_formats-cloud_config:

Cloud config
============

Example
-------

.. code-block:: yaml

    #cloud-config
    password: password
    chpasswd:
      expire: False

Explanation
-----------

Cloud-config can be used to define how an instance should be configured
in a human-friendly format. The cloud config format uses `YAML`_ with
keys which describe desired instance state.

These things may include:

- performing package upgrades on first boot
- configuration of different package mirrors or sources
- initial user or group setup
- importing certain SSH keys or host keys
- *and many more...*

Many modules are available to process cloud-config data. These modules
may run once per instance, every boot, or once ever. See the associated
module to determine the run frequency.

See the :ref:`cloud-config reference<modules>` and
:ref:`example configurations <yaml_examples>` for more details.

.. _YAML: https://yaml.org/spec/1.1/current.html
