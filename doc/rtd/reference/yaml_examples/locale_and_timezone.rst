.. _cce-locale-timezone:

Set system locale and timezone
******************************

Configure the system locale and timezone. For a full list of keys, refer to
the :ref:`locale module <mod_cc_locale>` and the
:ref:`timezone module <mod_cc_timezone>` schema.

Set the system locale
=====================

By default, cloud-init uses the locale specified by the datasource.

Set the locale directly
-----------------------

.. literalinclude:: ../../../module-docs/cc_locale/example1.yaml
   :language: yaml
   :linenos:

Set the locale via config file
------------------------------

This example sets the locale to ``fr_CA`` in ``/etc/alternate_path/locale``.

.. literalinclude:: ../../../module-docs/cc_locale/example2.yaml
   :language: yaml
   :linenos:

Set the system timezone
=======================

.. literalinclude:: ../../../module-docs/cc_timezone/example1.yaml
   :language: yaml
   :linenos:

