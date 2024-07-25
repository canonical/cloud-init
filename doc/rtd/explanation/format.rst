.. _user_data_formats:

User data formats
*****************

User data is configuration data provided by a user of a cloud platform to an
instance at launch. User data can be passed to cloud-init in any of many
formats documented here. Each format will document a required header or
content-type that must be present in the user data to be recognized as that
format.

Configuration types
===================

User data can be categorized into **base config**
or **meta config**.

Base config
-----------

Any of the base configs will be used to directly configure the instance.
These include:

- `Cloud config data`_
- `User data script`_
- `Cloud boothook`_

Meta config
-----------

Meta configs serve as a container, template, or means to obtain or modify
a base config. These include

- `MIME multi-part archive`_
- `Cloud config archive`_
- `Jinja template`_
- `Include file`_
- `Gzip compressed content`_
- `Part handler`_

.. _user_data_formats-cloud_config:

Cloud config data
=================

| **Header:** #cloud-config
| **Content-Type:** text/cloud-config

**Example**

.. code-block:: yaml

    #cloud-config
    password: password
    chpasswd:
    expire: False

**Explanation**

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

See the :ref:`yaml_examples` section for a set of commented examples of
supported cloud config formats.

.. _user_data_script:

User data script
================

| **Header:** #!
| **Content-Type:** text/x-shellscript

**Example**

.. code-block:: shell

    #!/bin/sh
    echo "Hello World" > /var/tmp/output.txt

**Explanation**

A user data script is a single shell script to be executed once per instance.
User data scripts are run relatively late in the boot process, after most
other cloud-init modules have run.

.. _user_data_formats-cloud_boothook:

Cloud boothook
==============

| **Header:** #cloud-boothook
| **Content-Type:** text/cloud-boothook

**Simple Example**

.. code-block:: shell

   #cloud-boothook
   #!/bin/sh
   echo 192.168.1.130 us.archive.ubuntu.com > /etc/hosts

**Example of once-per-instance script**

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

**Explanation**

A cloud boothook is similar to a :ref:`user data script<user_data_script>`
in that it is a shell script run on boot. The boothook is different in that:

* It is run very early in boot, even before the ``cc_bootcmd`` module
* It is run on every boot
* The environment variable ``INSTANCE_ID`` is set to the current instance ID
  for use within the script.

MIME multi-part archive
=======================

| **Header:** Content-Type: multipart/mixed;
| **Content-Type:** multipart/mixed

**Example**

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

**Explanation**

Using a MIME multi-part file, the user can specify more than one type of data.

For example, both a user data script and a cloud-config type could be
specified.

Supported content-types are listed from the ``cloud-init`` subcommand
:command:`make-mime`:

.. code-block:: shell-session

    $ cloud-init devel make-mime --list-types

Example output:

.. code-block::

    cloud-boothook
    cloud-config
    cloud-config-archive
    cloud-config-jsonp
    jinja2
    part-handler
    x-include-once-url
    x-include-url
    x-shellscript
    x-shellscript-per-boot
    x-shellscript-per-instance
    x-shellscript-per-once

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

| **Header:** #cloud-config-archive
| **Content-Type:** text/cloud-config-archive

**Example**

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

**Explanation**

A cloud-config-archive is a way to specify more than one type of data
using YAML. It can be seen as an alternative to building a MIME multi-part
archive manually.

The format is a list of dictionaries.

Required fields:

* ``type``: The content type of the MIME part
* ``content``: The configuration for the MIME part

Optional fields:

* ``launch-index``: The EC2 Launch-Index header in the MIME part
* ``filename``: The filename of the Content-Disposition header in the MIME
  part. This does not correspond to any local system file.

All other fields will be added unedited to the MIME part as headers.

Jinja template
==============

| **Header:** ## template: jinja
| **Content-Type:** text/jinja

**Example cloud-config**

.. code-block:: yaml

   ## template: jinja
   #cloud-config
   runcmd:
     - echo 'Running on {{ v1.cloud_name }}' > /var/tmp/cloud_name

**Example user data script**

.. code-block:: shell

   ## template: jinja
   #!/bin/sh
   echo 'Current instance id: {{ v1.instance_id }}' > /var/tmp/instance_id

**Explanation**

`Jinja templating <https://jinja.palletsprojects.com/>`_ may be used for
cloud-config and user data scripts. Any
:ref:`instance-data variables<instance_metadata-keys>` may be used
as jinja template variables. Any jinja templated configuration must contain
the original header along with the new jinja header above it.

.. note::
    Use of Jinja templates is ONLY supported for cloud-config and user data
    scripts. Jinja templates are not supported for cloud-boothooks or
    meta configs.

.. _user_data_formats-part_handler:

Include file
============

| **Header:** #include
| **Content-Type:** text/x-include-url

**Example**

.. code-block:: text

    #include
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-run-cmds.txt
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-boot-cmds.txt

**Explanation**

An include file contains a list of URLs, one per line. Each of the URLs will
be read and their content can be any kind of user data format, both base
config and meta config. If an error occurs reading a file the remaining files
will not be read.

Gzip compressed content
=======================

| **Header** n/a
| **Content-Type** n/a

Content found to be gzip compressed will be uncompressed.
The uncompressed data will then be used as if it were not compressed.
This is typically useful because user data size may be limited based on
cloud platform.

Part handler
============

| **Header:** #part-handler
| **Content-Type:** text/part-handler

**Example**

.. literalinclude:: ../../examples/part-handler.txt
   :language: python
   :linenos:

**Explanation**

A part handler contains custom code for either supporting new
mime-types in multi-part user data or for overriding the existing handlers for
supported mime-types.

This must be Python code that contains a ``list_types`` function and a
``handle_part`` function.

The ``list_types`` function must return a list
of mime-types that this `part-handler` handles. Since MIME parts are
processed in order, a `part-handler` part must precede any parts with
mime-types it is expected to handle in the same user data.

``Cloud-init`` will then call the ``handle_part`` function once before it
handles any parts, once per part received, and once after all parts have been
handled. These additional calls allow for  initialisation or teardown before
or after receiving any parts.

The provided example can be used as a template for creating a custom part
handler. `This blog post`_ offers another example for more advanced usage.

.. _make-mime: https://github.com/canonical/cloud-init/blob/main/cloudinit/cmd/devel/make_mime.py
.. _YAML: https://yaml.org/spec/1.1/current.html
.. _This blog post: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html
