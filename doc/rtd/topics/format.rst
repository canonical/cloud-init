.. _user_data_formats:

*****************
User-Data Formats
*****************

User data that will be acted upon by cloud-init must be in one of the following
types.

Gzip Compressed Content
=======================

Content found to be gzip compressed will be uncompressed.
The uncompressed data will then be used as if it were not compressed.
This is typically useful because user-data is limited to ~16384 [#]_ bytes.

Mime Multi Part Archive
=======================

This list of rules is applied to each part of this multi-part file.
Using a mime-multi part file, the user can specify more than one type of data.

For example, both a user data script and a cloud-config type could be
specified.

Supported content-types are listed from the cloud-init subcommand make-mime::

    % cloud-init devel make-mime --list-types
    cloud-boothook
    cloud-config
    cloud-config-archive
    cloud-config-jsonp
    jinja2
    part-handler
    upstart-job
    x-include-once-url
    x-include-url
    x-shellscript


Helper subcommand to generate mime messages
-------------------------------------------

The cloud-init subcommand can generate MIME multi-part files: `make-mime`_.

``make-mime`` subcommand takes pairs of (filename, "text/" mime subtype)
separated by a colon (e.g. ``config.yaml:cloud-config``) and emits a MIME
multipart message to stdout.  An example invocation, assuming you have your
cloud config in ``config.yaml`` and a shell script in ``script.sh`` and want
to store the multipart message in ``user-data``::

    % cloud-init devel make-mime -a config.yaml:cloud-config -a script.sh:x-shellscript > user-data

.. _make-mime: https://github.com/canonical/cloud-init/blob/master/cloudinit/cmd/devel/make_mime.py


User-Data Script
================

Typically used by those who just want to execute a shell script.

Begins with: ``#!`` or ``Content-Type: text/x-shellscript`` when using a MIME
archive.

.. note::
   New in cloud-init v. 18.4: User-data scripts can also render cloud instance
   metadata variables using jinja templating. See
   :ref:`instance_metadata` for more information.

Example
-------

::

  $ cat myscript.sh

  #!/bin/sh
  echo "Hello World.  The time is now $(date -R)!" | tee /root/output.txt

  $ euca-run-instances --key mykey --user-data-file myscript.sh ami-a07d95c9

Include File
============

This content is a ``include`` file.

The file contains a list of urls, one per line. Each of the URLs will be read,
and their content will be passed through this same set of rules. Ie, the
content read from the URL can be gzipped, mime-multi-part, or plain text. If
an error occurs reading a file the remaining files will not be read.

Begins with: ``#include`` or ``Content-Type: text/x-include-url``  when using
a MIME archive.

Cloud Config Data
=================

Cloud-config is the simplest way to accomplish some things via user-data. Using
cloud-config syntax, the user can specify certain things in a human friendly
format.

These things include:

- apt upgrade should be run on first boot
- a different apt mirror should be used
- additional apt sources should be added
- certain SSH keys should be imported
- *and many more...*

.. note::
   This file must be valid yaml syntax.

See the :ref:`yaml_examples` section for a commented set of examples of
supported cloud config formats.

Begins with: ``#cloud-config`` or ``Content-Type: text/cloud-config`` when
using a MIME archive.

.. note::
   New in cloud-init v. 18.4: Cloud config data can also render cloud instance
   metadata variables using jinja templating. See
   :ref:`instance_metadata` for more information.

Upstart Job
===========

Content is placed into a file in ``/etc/init``, and will be consumed by upstart
as any other upstart job.

Begins with: ``#upstart-job`` or ``Content-Type: text/upstart-job`` when using
a MIME archive.

Cloud Boothook
==============

This content is ``boothook`` data. It is stored in a file under
``/var/lib/cloud`` and then executed immediately. This is the earliest ``hook``
available. Note, that there is no mechanism provided for running only once. The
boothook must take care of this itself.

It is provided with the instance id in the environment variable
``INSTANCE_ID``. This could be made use of to provide a 'once-per-instance'
type of functionality.

Begins with: ``#cloud-boothook`` or ``Content-Type: text/cloud-boothook`` when
using a MIME archive.

Part Handler
============

This is a ``part-handler``: It contains custom code for either supporting new
mime-types in multi-part user data, or overriding the existing handlers for
supported mime-types.  It will be written to a file in ``/var/lib/cloud/data``
based on its filename (which is generated).

This must be python code that contains a ``list_types`` function and a
``handle_part`` function. Once the section is read the ``list_types`` method
will be called. It must return a list of mime-types that this part-handler
handles.  Because mime parts are processed in order, a ``part-handler`` part
must precede any parts with mime-types it is expected to handle in the same
user data.

The ``handle_part`` function must be defined like:

.. code-block:: python

    def handle_part(data, ctype, filename, payload):
      # data = the cloudinit object
      # ctype = "__begin__", "__end__", or the mime-type of the part that is being handled.
      # filename = the filename of the part (or a generated filename if none is present in mime data)
      # payload = the parts' content

Cloud-init will then call the ``handle_part`` function once before it handles
any parts, once per part received, and once after all parts have been handled.
The ``'__begin__'`` and ``'__end__'`` sentinels allow the part handler to do
initialization or teardown before or after receiving any parts.

Begins with: ``#part-handler`` or ``Content-Type: text/part-handler`` when
using a MIME archive.

Example
-------

.. literalinclude:: ../../examples/part-handler.txt
   :language: python
   :linenos:

Also this `blog`_ post offers another example for more advanced usage.

Kernel Command Line
===================

When using the :ref:`datasource_nocloud` datasource, users can pass user data
via the kernel command line parameters. See the :ref:`datasource_nocloud`
datasource documentation for more details.

Disabling User-Data
===================

Cloud-init can be configured to ignore any user-data provided to instance.
This allows custom images to prevent users from accidentally breaking closed
appliances. Setting ``allow_userdata: false`` in the configuration will disable
cloud-init from processing user-data.

.. [#] See your cloud provider for applicable user-data size limitations...
.. _blog: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html

.. vi: textwidth=78
