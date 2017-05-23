.. _datasource_cloudsigma:

CloudSigma
==========

This datasource finds metadata and user-data from the `CloudSigma`_ cloud
platform.  Data transfer occurs through a virtual serial port of the
`CloudSigma`_'s VM and the presence of network adapter is **NOT** a
requirement, See `server context`_ in the public documentation for more
information.


Setting a hostname
------------------
By default the name of the server will be applied as a hostname on the first
boot.


Providing user-data
-------------------

You can provide user-data to the VM using the dedicated `meta field`_ in the
`server context`_ ``cloudinit-user-data``. By default *cloud-config* format is
expected there and the ``#cloud-config`` header could be omitted. However
since this is a raw-text field you could provide any of the valid `config
formats`_.

You have the option to encode your user-data using Base64. In order to do that
you have to add the ``cloudinit-user-data`` field to the ``base64_fields``.
The latter is a comma-separated field with all the meta fields whit base64
encoded values.

If your user-data does not need an internet connection you can create a `meta
field`_ in the `server context`_ ``cloudinit-dsmode`` and set "local" as
value.  If this field does not exist the default value is "net".


.. _CloudSigma: http://cloudsigma.com/
.. _server context: http://cloudsigma-docs.readthedocs.org/en/latest/server_context.html
.. _meta field: http://cloudsigma-docs.readthedocs.org/en/latest/meta.html
.. _config formats: http://cloudinit.readthedocs.org/en/latest/topics/format.html
.. vi: textwidth=78
