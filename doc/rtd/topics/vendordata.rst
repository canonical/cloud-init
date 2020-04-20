***********
Vendor Data
***********

Overview
========

Vendordata is data provided by the entity that launches an instance
(for example, the cloud provider).  This data can be used to
customize the image to fit into the particular environment it is
being run in.

Vendordata follows the same rules as user-data, with the following
caveats:

 1. Users have ultimate control over vendordata. They can disable its
    execution or disable handling of specific parts of multipart input.
 2. By default it only runs on first boot
 3. Vendordata can be disabled by the user. If the use of vendordata is
    required for the instance to run, then vendordata should not be used.
 4. user supplied cloud-config is merged over cloud-config from vendordata.

Users providing cloud-config data can use the '#cloud-config-jsonp' method to
more finely control their modifications to the vendor supplied cloud-config.
For example, if both vendor and user have provided 'runcmd' then the default
merge handler will cause the user's runcmd to override the one provided by the
vendor.  To append to 'runcmd', the user could better provide multipart input
with a cloud-config-jsonp part like:

.. code:: yaml

 #cloud-config-jsonp
 [{ "op": "add", "path": "/runcmd", "value": ["my", "command", "here"]}]

Further, we strongly advise vendors to not 'be evil'. By evil, we
mean any action that could compromise a system. Since users trust
you, please take care to make sure that any vendordata is safe,
atomic, idempotent and does not put your users at risk.

Input Formats
=============

cloud-init will download and cache to filesystem any vendor-data that it
finds.  Vendordata is handled exactly like user-data.  That means that the
vendor can supply multipart input and have those parts acted on in the same
way as user-data.

The only differences are:

 * user-scripts are stored in a different location than user-scripts (to
   avoid namespace collision)
 * user can disable part handlers by cloud-config settings.
   For example, to disable handling of 'part-handlers' in vendor-data,
   the user could provide user-data like this:

   .. code:: yaml

    #cloud-config
    vendordata: {excluded: 'text/part-handler'}

Examples
========
There are examples in the examples subdirectory.

Additionally, the 'tools' directory contains 'write-mime-multipart',
which can be used to easily generate mime-multi-part files from a list
of input files.  That data can then be given to an instance.

See 'write-mime-multipart --help' for usage.

.. vi: textwidth=78
