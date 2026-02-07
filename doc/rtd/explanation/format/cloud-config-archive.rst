.. _cloud-config-archive:

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
using YAML. Since building a MIME multipart archive can be somewhat unwieldy
to build by hand or requires using a cloud-init helper utility, the
cloud-config-archive provides a simpler alternative to building the MIME
multi-part archive for those that would prefer to use YAML.

The format is a list of dictionaries.

Required fields:

* ``type``: The :ref:`Content-Type<user_data_formats-content_types>`
  identifier for the type of user-data in content
* ``content``: The user-data configuration

Optional fields:

* ``launch-index``: The EC2 Launch-Index (if applicable)
* ``filename``: This field is only used if using a user-data format that
  requires a filename in a MIME part. This is unrelated to any local system
  file.

All other fields will be interpreted as a MIME part header.

