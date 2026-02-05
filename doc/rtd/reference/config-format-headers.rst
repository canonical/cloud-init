:orphan:

.. _user_data_headers:

Headers and content types
=========================

A user-data header is required for cloud-init to recognize the format. See the
header and content types for each user-data format below:

+--------------------+-----------------------------+-------------------------+
|User-data format    |Header                       |Content-Type             |
+====================+=============================+=========================+
|Cloud config data   |#cloud-config                |text/cloud-config        |
+--------------------+-----------------------------+-------------------------+
|User-data script    |#!                           |text/x-shellscript       |
+--------------------+-----------------------------+-------------------------+
|Cloud boothook      |#cloud-boothook              |text/cloud-boothook      |
+--------------------+-----------------------------+-------------------------+
|MIME multi-part     |Content-Type: multipart/mixed|multipart/mixed          |
+--------------------+-----------------------------+-------------------------+
|Cloud config archive|#cloud-config-archive        |text/cloud-config-archive|
+--------------------+-----------------------------+-------------------------+
|Jinja template      |## template: jinja           |text/jinja2              |
+--------------------+-----------------------------+-------------------------+
|Include file        |#include                     |text/x-include-url       |
+--------------------+-----------------------------+-------------------------+
|Part handler        |#part-handler                |text/part-handler        |
+--------------------+-----------------------------+-------------------------+

.. note::

   The gzip format is not included above because it is binary data. It is
   identified by its magic bytes.

