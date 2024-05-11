.. _cce-apt-pipeline:

APT pipelining
**************

For a full list of keys, refer to the `APT pipelining module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    apt_pipelining: false

Example 2
=========

.. code-block:: yaml

    #cloud-config
    apt_pipelining: os

Example 3
=========

.. code-block:: yaml

    #cloud-config
    apt_pipelining: 3

.. LINKS
.. _APT pipelining module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apt-pipelining
