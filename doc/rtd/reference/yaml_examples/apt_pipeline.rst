.. _cce-apt-pipeline:

APT pipelining
**************

For a full list of keys, refer to the
:ref:`APT pipelining module <mod_cc_apt_pipelining>` schema.

Example 1
=========

This example disables pipelining.

.. literalinclude:: ../../../module-docs/cc_apt_pipelining/example1.yaml
   :language: yaml
   :linenos:

Example 2
=========

This setting is the default -- uses the default for the distribution.

.. literalinclude:: ../../../module-docs/cc_apt_pipelining/example2.yaml
   :language: yaml
   :linenos:

Example 3
=========

Manually specify a pipeline depth of three. This method is not recommended.

.. literalinclude:: ../../../module-docs/cc_apt_pipelining/example3.yaml
   :language: yaml
   :linenos:

