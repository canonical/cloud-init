.. _cce-write-files:

Writing out arbitrary files
***************************

Encoding can be given as base64 (b64) or gzip. The content will be decoded
accordingly and then written to the path provided.

For a full list of keys, refer to the
:ref:`write files module <mod_cc_write_files>` schema.

Write content to file
=====================

This example will write out base64-encoded content to
``/etc/sysconfig/selinux``.

.. literalinclude:: ../../../module-docs/cc_write_files/example1.yaml
   :language: yaml
   :linenos:

Append content to file
======================

This config will append content to an existing file.

.. literalinclude:: ../../../module-docs/cc_write_files/example2.yaml
   :language: yaml
   :linenos:

Provide gzipped binary content
==============================

.. literalinclude:: ../../../module-docs/cc_write_files/example3.yaml
   :language: yaml
   :linenos:

Create empty file on the system
===============================

.. literalinclude:: ../../../module-docs/cc_write_files/example4.yaml
   :language: yaml
   :linenos:

Defer writing content
=====================

This example shows how to defer writing the file until after the packages have
been installed and its user is created alongside.

.. literalinclude:: ../../../module-docs/cc_write_files/example5.yaml
   :language: yaml
   :linenos:

