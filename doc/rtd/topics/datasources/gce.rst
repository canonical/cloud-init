.. _datasource_gce:

Google Compute Engine
=====================

The GCE datasource gets its data from the internal compute metadata server.
Metadata can be queried at the URL
'``http://metadata.google.internal/computeMetadata/v1/``'
from within an instance.  For more information see the `GCE metadata docs`_.

Currently the default project and instance level metadatakeys keys
``project/attributes/sshKeys`` and ``instance/attributes/ssh-keys`` are merged
to provide ``public-keys``.

``user-data`` and ``user-data-encoding`` can be provided to cloud-init by
setting those custom metadata keys for an *instance*.

.. _GCE metadata docs: https://cloud.google.com/compute/docs/storing-retrieving-metadata#querying

.. vi: textwidth=78
