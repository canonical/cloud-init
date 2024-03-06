.. _datasource_gce:

Google Compute Engine
*********************

The GCE datasource gets its data from the internal compute metadata server.
Metadata can be queried at the URL
:file:`http://metadata.google.internal/computeMetadata/v1/`
from within an instance. For more information see the `GCE metadata docs`_.

Currently, the default project and instance level metadata keys
``project/attributes/sshKeys`` and ``instance/attributes/ssh-keys`` are merged
to provide ``public-keys``.

``user-data`` and ``user-data-encoding`` can be provided to ``cloud-init`` by
setting those custom metadata keys for an *instance*.

Configuration
=============

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

* ``retries``

  The number of retries that should be attempted for a http request.
  This value is used only after ``metadata_url`` is selected.

  Default: 5

* ``sec_between_retries``

  The amount of wait time between retries when crawling the metadata service.

  Default: 1

Example
-------

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
     GCE:
       retries: 5
       sec_between_retries: 1

.. _GCE metadata docs: https://cloud.google.com/compute/docs/storing-retrieving-metadata
