How to identify the datasource I'm using
========================================

To correctly set up an instance, ``cloud-init`` must correctly identify the
cloud it is on. Therefore, knowing which datasource is being used on an
instance launch can aid in debugging.

To find out which datasource is being used run the :command:`cloud-id` command:

.. code-block:: bash

   cloud-id

This will tell you which datasource is being used -- for example:

.. code-block::

   nocloud

If the ``cloud-id`` is not what is expected, then running the
:file:`ds-identify` script in debug mode and providing that in a bug report can
aid in resolving any issues:

.. code-block:: bash

   sudo DEBUG_LEVEL=2 DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force

The ``force`` parameter allows the command to be run again since the instance
has already launched. The other options increase the verbosity of logging and
outputs the logs to :file:`STDERR`.
