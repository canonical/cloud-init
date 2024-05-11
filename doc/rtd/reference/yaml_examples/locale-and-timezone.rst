.. _cce-locale-timezone:

Set system locale and timezone
******************************

Configure the system locale and timezone. For a full list of keys, refer to
the `locale module`_ and the `timezone module`_ schema.

Set the system locale
=====================

By default, cloud-init uses the locale specified by the datasource.

Set the locale directly
-----------------------

.. code-block:: yaml

    #cloud-config
    locale: ar_AE

Set the locale via config file
------------------------------

This example sets the locale to ``fr_CA`` in ``/etc/alternate_path/locale``.

.. code-block:: yaml

    #cloud-config
    locale: fr_CA
    locale_configfile: /etc/alternate_path/locale

Set the system timezone
=======================

.. code-block:: yaml

    #cloud-config
    timezone: US/Eastern


.. LINKS
.. _locale module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#locale
.. _timezone module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#timezone

