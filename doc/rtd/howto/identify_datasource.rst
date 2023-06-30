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

How can I re-run datasource detection and ``cloud-init``?
---------------------------------------------------------

If you are developing a new datasource or working on debugging an issue it
may be useful to re-run datasource detection and the initial setup of
``cloud-init``.

.. warning::

    **Do not run the following commands on production systems.**

    These commands will re-run ``cloud-init`` as if this were first boot of a
    system. At the very least, this will cycle SSH host keys but may do
    substantially more.

To re-run datasource detection, you must first force :file:`ds-identify` to
re-run, then clean up any logs, and finally, re-run ``cloud-init``:

.. code-block:: bash

   sudo DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force
   sudo cloud-init clean --logs
   sudo cloud-init init --local
   sudo cloud-init init
