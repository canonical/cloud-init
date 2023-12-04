.. _failure_states:

Failure states
==============

Cloud-init has multiple modes of failure. This page describes these
modes and how to gather information about failures.

.. _critical_failure:

Critical failure
----------------

Critical failures happens when cloud-init experiences a condition that it
cannot safely handle. When this happens, cloud-init may be unable to complete,
and the instance is likely to be in an unknown broken state.

Cloud-init experiences critical failure when:

* there is a major problem with the cloud image that is running cloud-init
* there is a severe bug in cloud-init

When this happens, error messages will be visible in output of
``cloud-init status --long`` within the ``'error'``.

The same errors will also be located under the key nested under the
module-level keys that store information related to each
:ref:`stage of cloud-init<boot_stages>`: ``init-local``, ``init``,
``modules-config``, ``modules-final``.

.. _recoverable_failure:

Recoverable failure
-------------------

In the case that cloud-init is able to complete yet something went wrong,
cloud-init has experienced a "recoverable failure". When this happens,
the service will return with exit code 2, and error messages will be
visible in the output of ``cloud-init status --long`` under the top
level ``recoverable_errors`` and ``error`` keys.

To identify which stage an error came from, one can check under the
module-level keys: ``init-local``, ``init``, ``modules-config``,
``modules-final`` for the same error keys.

See :ref:`this more detailed explanation<exported_errors>` for to learn how to
use cloud-init's exported errors.

Cloud-init error codes
----------------------

Cloud-init's ``status`` subcommand is useful for understanding which type of
error cloud-init experienced while running. The return code will be one of the
following:

.. code-block:: shell-session

    0 - success
    1 - unrecoverable error
    2 - recoverable error

If ``cloud-init status`` exits with exit code 1, cloud-init experienced
critical failure and was unable to recover. In this case, something is likely
seriously wrong with the system, or cloud-init has experienced a serious bug.
If you believe that you have experienced a serious bug, please file a
:ref:`bug report<reporting_bugs>`.

If cloud-init exits with exit code 2, cloud-init was able to complete
gracefully, however something went wrong and the user should investigate.

See :ref:`this more detailed explanation<reported_status>` for more information
on cloud-init's status.

Where to next?
--------------

See :ref:`our more detailed guide<how_to_debug>` for a detailed guide to
debugging cloud-init.
