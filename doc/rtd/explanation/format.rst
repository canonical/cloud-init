.. _user_data_formats:

User data formats
*****************

User data is configuration data provided by a user of a cloud platform to an
instance at launch. User data can be passed to cloud-init in any of many
formats documented here.

Configuration types
===================

User data formats can be categorized into those that directly configure the
instance, and those that serve as a container, template, or means to obtain
or modify another configuration.

Formats that directly configure the instance:

- `Cloud config data`_
- `User data script`_
- `Cloud boothook`_

Formats that deal with other user data formats:

- `Include file`_
- `Jinja template`_
- `MIME multi-part archive`_
- `Cloud config archive`_
- `Part handler`_
- `Gzip compressed content`_

.. _user_data_formats-cloud_config:

Cloud config data
=================

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

For more information, see the cloud config
:ref:`example configurations <yaml_examples>` or the cloud config
:ref:`modules reference<modules>`.

.. _user_data_script:

User data script
================

Example
-------

.. code-block:: shell

    #!/bin/sh
    echo "Hello World" > /var/tmp/output.txt

Explanation
-----------

A user data script is a single script to be executed once per instance.
User data scripts are run relatively late in the boot process, during
cloud-init's :ref:`final stage<boot-Final>` as part of the
:ref:`cc_scripts_user<mod_cc_scripts_user>` module. When run,
the environment variable ``INSTANCE_ID`` is set to the current instance ID
for use within the script.

.. _user_data_formats-cloud_boothook:

Cloud boothook
==============

Simple Example
--------------

.. code-block:: shell

   #cloud-boothook
   #!/bin/sh
   echo 192.168.1.130 us.archive.ubuntu.com > /etc/hosts

Example of once-per-instance script
-----------------------------------

.. code-block:: bash

   #cloud-boothook
   #!/bin/sh

   PERSIST_ID=/var/lib/cloud/first-instance-id
   _id=""
   if [ -r $PERSIST_ID ]; then
     _id=$(cat /var/lib/cloud/first-instance-id)
   fi

   if [ -z $_id ]  || [ $INSTANCE_ID != $_id ]; then
     echo 192.168.1.130 us.archive.ubuntu.com >> /etc/hosts
   fi
   sudo echo $INSTANCE_ID > $PERSIST_ID

Explanation
-----------

A cloud boothook is similar to a :ref:`user data script<user_data_script>`
in that it is a script run on boot. When run,
the environment variable ``INSTANCE_ID`` is set to the current instance ID
for use within the script.

The boothook is different in that:

* It is run very early in boot, during the :ref:`network<boot-Network>` stage,
  before any cloud-init modules are run.
* It is run on every boot

Include file
============

Example
-------

.. code-block:: text

    #include
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-run-cmds.txt
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-boot-cmds.txt

Explanation
-----------

An include file contains a list of URLs, one per line. Each of the URLs will
be read and their content can be any kind of user data format, both base
config and meta config. If an error occurs reading a file the remaining files
will not be read.

Jinja template
==============

Example cloud-config
--------------------

.. code-block:: yaml

   ## template: jinja
   #cloud-config
   runcmd:
     - echo 'Running on {{ v1.cloud_name }}' > /var/tmp/cloud_name

Example user data script
------------------------

.. code-block:: shell

   ## template: jinja
   #!/bin/sh
   echo 'Current instance id: {{ v1.instance_id }}' > /var/tmp/instance_id

Explanation
-----------

`Jinja templating <https://jinja.palletsprojects.com/>`_ may be used for
cloud-config and user data scripts. Any
:ref:`instance-data variables<instance_metadata-keys>` may be used
as jinja template variables. Any jinja templated configuration must contain
the original header along with the new jinja header above it.

.. note::
    Use of Jinja templates is ONLY supported for cloud-config and user data
    scripts. Jinja templates are not supported for cloud-boothooks or
    meta configs.

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

For example, both a user data script and a cloud-config type could be
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

Create user data containing both a cloud-config (:file:`config.yaml`)
and a shell script (:file:`script.sh`)

.. code-block:: shell-session

    $ cloud-init devel make-mime -a config.yaml:cloud-config -a script.sh:x-shellscript > userdata

Create user data containing 3 shell scripts:

- :file:`always.sh` - run every boot
- :file:`instance.sh` - run once per instance
- :file:`once.sh` - run once

.. code-block:: shell-session

    $ cloud-init devel make-mime -a always.sh:x-shellscript-per-boot -a instance.sh:x-shellscript-per-instance -a once.sh:x-shellscript-per-once


Cloud config archive
====================

Example
-------

.. code-block:: shell

    #cloud-config-archive
    - type: "text/cloud-boothook"
      content: |
        #!/bin/sh
        echo "this is from a boothook." > /var/tmp/boothook.txt
    - type: "text/cloud-config"
      content: |
        bootcmd:
        - echo "this is from a cloud-config." > /var/tmp/bootcmd.txt

Explanation
-----------

A cloud-config-archive is a way to specify more than one type of data
using YAML. Since building a MIME multipart archive can be somewhat unwieldly
to build by hand or requires using a cloud-init helper utility, the
cloud-config-archive provides a simpler alternative to building the MIME
multi-part archive for those that would prefer to use YAML.

The format is a list of dictionaries.

Required fields:

* ``type``: The :ref:`Content-Type<user_data_formats-content_types>`
  identifier for the type of user data in content
* ``content``: The user data configuration

Optional fields:

* ``launch-index``: The EC2 Launch-Index (if applicable)
* ``filename``: This field is only used if using a user data format that
  requires a filename in a MIME part. This is unrelated to any local system
  file.

All other fields will be interpreted as a MIME part header.

.. _user_data_formats-part_handler:

Part handler
============

Example
-------

.. literalinclude:: ../../examples/part-handler.txt
   :language: python
   :linenos:


Explanation
-----------

A part handler contains custom code for either supporting new
mime-types in multi-part user data or for overriding the existing handlers for
supported mime-types.

See the :ref:`custom part handler<custom_part_handler>` reference documentation
for details on writing custom handlers along with an annotated example.

`This blog post`_ offers another example for more advanced usage.

Gzip compressed content
=======================

Content found to be gzip compressed will be uncompressed.
The uncompressed data will then be used as if it were not compressed.
This is typically useful because user data size may be limited based on
cloud platform.

.. _user_data_formats-content_types:

Headers and content types
=========================

In order for cloud-init to recognize which user data format is being used,
the user data must contain a header. Additionally, if the user data
is being passed as a multi-part message, such as MIME, cloud-config-archive,
or part-handler, the content-type for each part must also be set
appropriately.

The table below lists the headers and content types for each user data format.
Note that gzip compressed content is not represented here as it gets passed
as binary data and so may be processed automatically.

+--------------------+-----------------------------+-------------------------+
|User data format    |Header                       |Content-Type             |
+====================+=============================+=========================+
|Cloud config data   |#cloud-config                |text/cloud-config        |
+--------------------+-----------------------------+-------------------------+
|User data script    |#!                           |text/x-shellscript       |
+--------------------+-----------------------------+-------------------------+
|Cloud boothook      |#cloud-boothook              |text/cloud-boothook      |
+--------------------+-----------------------------+-------------------------+
|MIME multi-part     |Content-Type: multipart/mixed|multipart/mixed          |
+--------------------+-----------------------------+-------------------------+
|Cloud config archive|#cloud-config-archive        |text/cloud-config-archive|
+--------------------+-----------------------------+-------------------------+
|Jinja template      |## template: jinja           |text/jinja               |
+--------------------+-----------------------------+-------------------------+
|Include file        |#include                     |text/x-include-url       |
+--------------------+-----------------------------+-------------------------+
|Part handler        |#part-handler                |text/part-handler        |
+--------------------+-----------------------------+-------------------------+


.. _make-mime: https://github.com/canonical/cloud-init/blob/main/cloudinit/cmd/devel/make_mime.py
.. _YAML: https://yaml.org/spec/1.1/current.html
.. _This blog post: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html
