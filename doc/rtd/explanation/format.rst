.. _user_data_formats:

User data formats
*****************

User data that will be acted upon by ``cloud-init`` must be in one of the
following types.

.. _user_data_formats-cloud_config:

Cloud config data
=================

Cloud-config is the simplest way to accomplish some things via user data.
Using cloud-config syntax, a YAML configuration, the user can specify
certain things in a human-friendly format.

These things include:

- ``apt upgrade`` should be run on first boot
- a different ``apt`` mirror should be used
- additional ``apt`` sources should be added
- certain SSH keys should be imported
- *and many more...*

Begins with: ``#cloud-config``.

See the :ref:`yaml_examples` section for a commented set of examples of
supported cloud config formats.

.. note::
   New in ``cloud-init`` v. 18.4: Cloud config data can also render cloud
   instance metadata variables using jinja templating. See
   :ref:`instance_metadata` for more information.

.. _user_data_script:

User data script
================

Typically used by those who just want to execute a shell script.


Example script
--------------

Create a script file :file:`myscript.sh` that contains the following:

Begins with: ``#!``.

.. code-block::

   #!/bin/sh
   echo "Hello World.  The time is now $(date -R)!" | tee /root/output.txt

Now run:

.. code-block:: shell-session

   $ euca-run-instances --key mykey --user-data-file myscript.sh ami-a07d95c9

.. note::
   User data scripts can optionally render cloud instance metadata variables using
   jinja templating. See :ref:`instance_metadata` for more information.


Kernel command line
===================

When using the NoCloud datasource, users can pass user data via the kernel
command line parameters. See the :ref:`NoCloud datasource<datasource_nocloud>`
and :ref:`kernel_cmdline` documentation for more details.

Gzip compressed content
=======================

Content found to be gzip compressed will be uncompressed.
The uncompressed data will then be used as if it were not compressed.
This is typically useful because user data is limited to ~16384 [#]_ bytes.

``include`` file
================

This content is an :file:`include` file.

The file contains a list of URLs, one per line. Each of the URLs will be read
and their content will be passed through this same set of rules, i.e., the
content read from the URL can be gzipped, MIME multi-part, or plain text. If
an error occurs reading a file the remaining files will not be read.

Begins with: ``#include``.

Example
-------

Include 3 files:
:file:`file/path/A`, :file:`file/path/B` and :file:`file/path/C`.

.. code-block::

   #include
   file/path/A
   file/path/B
   file/path/C


``cloud-boothook``
==================

This content is `boothook` data.
This is a valid script(bash, python etc.) that runs during every boot.

This is the earliest `hook`_ to run,
it runs during the :ref:`Network boot stage<boot-Network>`.

You can use this to configure some network configuration during boot.

Example with simple script
--------------------------

.. code-block:: bash

   #cloud-boothook
   #!/bin/sh

   sudo ufw enable
   sudo ufw logging on

   sudo ufw allow http
   sudo ufw allow "OpenSSH"

   sudo iptables -I DOCKER-USER -j ACCEPT

Note, there is no mechanism provided for running only once. The
`boothook` must take care of this itself.

It is provided with the instance id in the environment variable
``INSTANCE_ID``. This could be made use of to provide a 'once-per-instance'
type of functionality. An example of a `once-per-instance` script:

Begins with: ``#cloud-boothook``.

Example of once-per-instance script
-----------------------------------

.. code-block:: bash

   #cloud-boothook
   #!/bin/sh

   _id=""
   if [ -r /var/lib/my-instance-id ]
     then
       _id=$(cat /var/lib/my-instance-id)
   fi

   if [ -z $_id ]  || [ $INSTANCE_ID != $_id ]
       then
          sudo ufw enable
          sudo ufw logging on

          sudo ufw allow http
          sudo ufw allow "OpenSSH"

          sudo iptables -I DOCKER-USER -j ACCEPT
   fi
   sudo echo $INSTANCE_ID > /var/lib/my-instance-id

MIME multi-part archive
=======================

This list of rules is applied to each part of this multi-part file.
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

User data format to Mime Content type mapping
---------------------------------------------

We use the following format to outline the content-type the user is
using

.. code-block::

   Content-Type: text/<content-type>

Below is a mapping of a specific user data format to the `content-type`
value to use when using the mime multipart archive format.


+----------------------------+----------------------------+
| User data                  | Content Type               |
+============================+============================+
| cloud boothook             | cloud-boothook             |
+----------------------------+----------------------------+
| cloud config               | cloud-config               |
+----------------------------+----------------------------+
| cloud config archive       | cloud-config-archive       |
+----------------------------+----------------------------+
| cloud config jsonp         | cloud-config-jsonp         |
+----------------------------+----------------------------+
| Jinja2                     | jinja2                     |
+----------------------------+----------------------------+
| User data script           | x-shellscript              |
+----------------------------+----------------------------+
| include file               | x-include-url              |
+----------------------------+----------------------------+
| include file once          | x-include-once-url         |
+----------------------------+----------------------------+
| Part handler               | part-handler               |
+----------------------------+----------------------------+
| x-shellscript-per-instance | x-shellscript-per-instance |
+----------------------------+----------------------------+
| x-shellscript-per-once     | x-shellscript-per-once     |
+----------------------------+----------------------------+
| x-shellscript-per-boot     | x-shellscript-per-boot     |
+----------------------------+----------------------------+

Examples
--------

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

Part-handler
============

This is a `part-handler`: It contains custom code for either supporting new
mime-types in multi-part user data, or overriding the existing handlers for
supported mime-types.  It will be written to a file in
:file:`/var/lib/cloud/data` based on its filename (which is generated).

This must be Python code that contains a ``list_types`` function and a
``handle_part`` function. Once the section is read the ``list_types`` method
will be called. It must return a list of mime-types that this `part-handler`
handles. Since MIME parts are processed in order, a `part-handler` part
must precede any parts with mime-types it is expected to handle in the same
user data.

The ``handle_part`` function must be defined like:

.. code-block:: python

    def handle_part(data, ctype, filename, payload):
      # data = the cloudinit object
      # ctype = "__begin__", "__end__", or the mime-type of the part that is being handled.
      # filename = the filename of the part (or a generated filename if none is present in mime data)
      # payload = the parts' content

``Cloud-init`` will then call the ``handle_part`` function once before it
handles any parts, once per part received, and once after all parts have been
handled. The ``'__begin__'`` and ``'__end__'`` sentinels allow the part
handler to do initialisation or teardown before or after receiving any parts.

Begins with: ``#part-handler``.

Example
-------

.. literalinclude:: ../../examples/part-handler.txt
   :language: python
   :linenos:

Also, `this blog post`_ offers another example for more advanced usage.

Disabling user data
===================

``Cloud-init`` can be configured to ignore any user data provided to instance.
This allows custom images to prevent users from accidentally breaking closed
appliances. Setting ``allow_userdata: false`` in the configuration will disable
``cloud-init`` from processing user data.

.. _make-mime: https://github.com/canonical/cloud-init/blob/main/cloudinit/cmd/devel/make_mime.py
.. [#] See your cloud provider for applicable user-data size limitations...
.. _hook: https://en.wikipedia.org/wiki/Hooking
.. _this blog post: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html
