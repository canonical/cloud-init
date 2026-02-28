.. _gzip:

Gzip compressed content
=======================

Content found to be gzip compressed will be uncompressed.
The uncompressed data will then be used as if it were not compressed.
This may be useful when user-data size may be limited based on
cloud platform.

Some platforms are known to corrupt binary content, which prevents using
this format.

.. _user_data_formats-content_types:

