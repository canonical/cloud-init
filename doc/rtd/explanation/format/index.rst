.. _user_data_formats:

User-data formats
*****************

User-data encodes instructions used by cloud-init. User-data has multiple
configuration types. Each type is identified by a
:ref:`unique header <user_data_headers>`.

Configuration types
===================

User-data formats can be categorized into those that directly configure the
instance, and those that serve as a container, template, or means to obtain
or modify another configuration.

Formats that directly configure the instance:

- :ref:`Cloud-config <user_data_formats-cloud_config>`
- :ref:`User-data script <user_data_script>`
- :ref:`Boothook <user_data_formats-cloud_boothook>`

Formats that embed other formats:

- :ref:`Include <user_data_formats-include>`
- :ref:`Jinja <user_data_formats-jinja>`
- :ref:`MIME <user_data_formats-mime_archive>`
- :ref:`Cloud-config archive <cloud-config-archive>`
- :ref:`Gzip <gzip>`

.. toctree::
   :hidden:

   Cloud-config <cloud-config>
   Boothook <boothook>
   User-data script <user-data-script>
   Include <include>
   Jinja <jinja>
   Gzip <gzip>
   Cloud-config archive <cloud-config-archive>
   MIME <mime>

Continued reading
=================

See the :ref:`configuration sources<configuration>` documentation for
information about configuration sources and priority.
