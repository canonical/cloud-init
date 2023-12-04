.. _reported_status:

Reported status
===============

When interacting with cloud-init, it may be useful to know whether
cloud-init has run, or is currently running. Since cloud-init consists
of several different stages, interacting directly with your init system might
yield different reported results than one might expect, unless one has intimate
knowledge of cloud-init's :ref:`boot stages<boot_stages>`.

Cloud-init status
-----------------

To simplify this, cloud-init provides a tool, ``cloud-init status`` to
report the current status of cloud-init.

.. code-block:: shell-session

    $ cloud-init status
    "done"

Cloud-init's extended status
----------------------------

Cloud-init is also capable of reporting when cloud-init has not been
able to complete the tasks described in a user configuration. If cloud-init
has experienced issues while running, the extended status will include the word
"degraded" in its status.

Cloud-init can report its internal state via the ``status --format json``
subcommand under the ``extended_status`` key.

.. code-block:: shell-session
    :emphasize-lines: 7

    $ cloud-init status --format json
    {
      "boot_status_code": "enabled-by-generator",
      "datasource": "",
      "detail": "Cloud-init enabled by systemd cloud-init-generator",
      "errors": [],
      "extended_status": "degraded done",
      "last_update": "",
      "recoverable_errors": {},
      "status": "done"
    }

See the list of all possible reported statuses:

.. code-block:: shell-session

    "not running"
    "running"
    "done"
    "error"
    "degraded done"
    "degraded running"
    "disabled"

See :ref:`our explanation of failure states<failure_states>` for more
information.
