.. _user_data_formats-mime_archive:

MIME multi-part archive
=======================

Example
-------

.. code-block::

    Content-Type: multipart/mixed; boundary="===============2389165605550749110=="
    MIME-Version: 1.0
    Number-Attachments: 2

    --===============2389165605550749110==
    Content-Type: text/cloud-boothook; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: attachment; filename="part-001"

    #!/bin/sh
    echo "this is from a boothook." > /var/tmp/boothook.txt

    --===============2389165605550749110==
    Content-Type: text/cloud-config; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: attachment; filename="part-002"

    bootcmd:
    - echo "this is from a cloud-config." > /var/tmp/bootcmd.txt
    --===============2389165605550749110==--

Explanation
-----------

Using a MIME multi-part file, the user can specify more than one type of data.

For example, both a user-data script and a cloud-config type could be
specified.

Each part must specify a valid
:ref:`content types<user_data_formats-content_types>`. Supported content-types
may also be listed from the ``cloud-init`` subcommand
:command:`make-mime`:

.. code-block:: shell-session

    $ cloud-init devel make-mime --list-types

Helper subcommand to generate MIME messages
-------------------------------------------

The ``cloud-init`` `make-mime`_ subcommand can also generate MIME multi-part
files.

The :command:`make-mime` subcommand takes pairs of (filename, "text/" mime
subtype) separated by a colon (e.g., ``config.yaml:cloud-config``) and emits a
MIME multipart message to :file:`stdout`.

**MIME subcommand Examples**

Create user-data containing both a cloud-config (:file:`config.yaml`)
and a shell script (:file:`script.sh`)

.. code-block:: shell-session

    $ cloud-init devel make-mime -a config.yaml:cloud-config -a script.sh:x-shellscript > user-data.mime

Create user-data containing 3 shell scripts:

- :file:`always.sh` - run every boot
- :file:`instance.sh` - run once per instance
- :file:`once.sh` - run once

.. code-block:: shell-session

    $ cloud-init devel make-mime -a always.sh:x-shellscript-per-boot -a instance.sh:x-shellscript-per-instance -a once.sh:x-shellscript-per-once

Per-frequency shell scripts
---------------------------

Cloud-init supports three MIME content types for controlling how often a
shell script runs:

``text/x-shellscript-per-boot``
    The script runs on **every boot**. Useful for tasks that must be
    repeated each time the instance starts, such as mounting ephemeral
    storage or refreshing dynamic configuration.

``text/x-shellscript-per-instance``
    The script runs **once per instance** (on first boot only). Useful
    for one-time instance setup tasks.

``text/x-shellscript-per-once``
    The script runs **exactly once**, even across different instances
    created from the same image. Useful for tasks that should never
    repeat regardless of instance lifecycle.

Scripts are stored on disk under the following directories:

- ``/var/lib/cloud/scripts/per-boot/``
- ``/var/lib/cloud/scripts/per-instance/``
- ``/var/lib/cloud/scripts/per-once/``

These are handled by :ref:`cc_scripts_per_boot<mod_cc_scripts_per_boot>`,
:ref:`cc_scripts_per_instance<mod_cc_scripts_per_instance>`, and
:ref:`cc_scripts_per_once<mod_cc_scripts_per_once>` respectively, via
``cloudinit/handlers/shell_script_by_frequency.py``.

.. _make-mime: https://github.com/canonical/cloud-init/blob/main/cloudinit/cmd/devel/make_mime.py
