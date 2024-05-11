.. _cce-seed-random:

Provide random seed data
************************

For a full list of keys, refer to the `seed random module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    random_seed:
      file: /dev/urandom
      data: my random string
      encoding: raw
      command: ['sh', '-c', 'dd if=/dev/urandom of=$RANDOM_SEED_FILE']
      command_required: true

Example 2
=========

This example uses ``pollinate`` to gather data from a remote entropy server,
and writes that data to ``/dev/urandom``:

.. code-block:: yaml

    #cloud-config
    random_seed:
      file: /dev/urandom
      command: ["pollinate", "--server=http://local.polinate.server"]
      command_required: true

.. LINKS
.. _seed random module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#seed-random
