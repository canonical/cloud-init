.. _vendordata:

Vendor data
***********

Overview
========

Vendor data is data provided by the entity that launches an instance (e.g.,
the cloud provider). This data can be used to customise the image to fit into
the particular environment it is being run in.

Vendor data follows the same rules as user data, with the following
caveats:

1. Users have ultimate control over vendor data. They can disable its
   execution or disable handling of specific parts of multi-part input.
2. By default it only runs on first boot.
3. Vendor data can be disabled by the user. If the use of vendor data is
   required for the instance to run, then vendor data should not be used.
4. User-supplied cloud-config is merged over cloud-config from vendor data.

Users providing cloud-config data can use the ``#cloud-config-jsonp`` method
to more finely control their modifications to the vendor-supplied
cloud-config. For example, if both vendor and user have provided ``runcmd``
then the default merge handler will cause the user's ``runcmd`` to override
the one provided by the vendor. To append to ``runcmd``, the user could better
provide multi-part input with a ``cloud-config-jsonp`` part like:

.. code:: yaml

   #cloud-config-jsonp
   [{ "op": "add", "path": "/runcmd", "value": ["my", "command", "here"]}]

Further, we strongly advise vendors to not "be evil". By evil, we mean any
action that could compromise a system. Since users trust you, please take
care to make sure that any vendor data is safe, atomic, idempotent and does
not put your users at risk.

Input formats
=============

``Cloud-init`` will download and cache to filesystem any vendor data that it
finds. Vendor data is handled exactly like user data. This means that the
vendor can supply multi-part input and have those parts acted on in the same
way as with user data.

The only differences are:

* Vendor-data-defined scripts are stored in a different location than
  user-data-defined scripts (to avoid namespace collision).
* The user can disable part handlers via the cloud-config settings.
  For example, to disable handling of 'part-handlers' in vendor data,
  the user could provide user data like this:

.. code:: yaml

    #cloud-config
    vendordata: {excluded: 'text/part-handler'}

Examples
========

You can find examples in the examples subdirectory.

Additionally, the :file:`tools` directory contains
:file:`write-mime-multipart`, which can be used to easily generate MIME
multi-part files from a list of input files. That data can then be given to
an instance.

See :command:`write-mime-multipart --help` for usage.
