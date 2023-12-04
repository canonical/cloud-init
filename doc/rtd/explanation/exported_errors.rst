.. _exported_errors:

Exported errors
===============

Cloud-init makes internal errors available to users for debugging. These
errors map to logged errors and may be useful for understanding what
happens when cloud-init doesn't do what you expect.

Aggregated errors
-----------------

When a :ref:`recoverable error<recoverable_failure>` occurs, the internal
cloud-init state information is made visible under a top level aggregate key
``recoverable_errors`` with errors sorted by error level:

.. code-block:: shell-session
    :emphasize-lines: 11-19

    $ cloud-init status --format json
    {
      "boot_status_code": "enabled-by-generator",
      "config": {...},
      "datasource": "",
      "detail": "Cloud-init enabled by systemd cloud-init-generator",
      "errors": [],
      "extended_status": "degraded done",
      "init": {...},
      "last_update": "",
      "recoverable_errors":
      {
        "WARNING": [
          "Failed at merging in cloud config part from p-01: empty cloud config",
          "No template found in /etc/cloud/templates for template source.deb822",
          "No template found in /etc/cloud/templates for template sources.list",
          "No template found, not rendering /etc/apt/soures.list.d/ubuntu.source"
        ]
      },
      "status": "done"
    }


Reported recoverable error messages are grouped by the level at which
they are logged. Complete list of levels in order of increasing
criticality:

.. code-block:: shell-session

    WARNING
    DEPRECATED
    ERROR
    CRITICAL

Each message has a single level. In cloud-init's :ref:`log files<log_files>`,
the level at which logs are reported is configurable. These messages are
exported via the ``'recoverable_errors'`` key regardless of which level of
logging is configured.

Per-stage errors
----------------

The keys ``errors`` and ``recoverable_errors`` are also exported for each
stage to allow identifying when recoverable and non-recoverable errors
occurred.

.. code-block:: shell-session
    :emphasize-lines: 4-11,16-21

    $ cloud-init status --format json
    {
      "boot_status_code": "enabled-by-generator",
      "config":
      {
        "WARNING": [
          "No template found in /etc/cloud/templates for template source.deb822",
          "No template found in /etc/cloud/templates for template sources.list",
          "No template found, not rendering /etc/apt/soures.list.d/ubuntu.source"
        ]
      },
      "datasource": "",
      "detail": "Cloud-init enabled by systemd cloud-init-generator",
      "errors": [],
      "extended_status": "degraded done",
      "init":
      {
        "WARNING": [
          "Failed at merging in cloud config part from p-01: empty cloud config",
        ]
      },
      "last_update": "",
      "recoverable_errors":
      {
        "WARNING": [
          "Failed at merging in cloud config part from p-01: empty cloud config",
          "No template found in /etc/cloud/templates for template source.deb822",
          "No template found in /etc/cloud/templates for template sources.list",
          "No template found, not rendering /etc/apt/soures.list.d/ubuntu.source"
        ]
      },
      "status": "done"
    }

.. note::

    Only completed cloud-init stages are listed in the output of
    ``cloud-init status --format json``.

The JSON representation of cloud-init :ref:`boot stages<boot_stages>`
(in run order) is:

.. code-block:: shell-session

    "init-local"
    "init"
    "modules-config"
    "modules-final"

Limitations of exported errors
------------------------------

- Exported recoverable errors represent logged messages, which are not
  guaranteed to be stable between releases. The contents of the
  ``'errors'`` and ``'recoverable_errors'`` keys are not guaranteed to have
  stable output.
- Exported errors and recoverable errors may occur at different stages
  since users may reorder configuration modules to run at different
  stages via :file:`cloud.cfg`.

Where to next?
--------------
See :ref:`here<how_to_debug>` for a detailed guide to debugging cloud-init.
