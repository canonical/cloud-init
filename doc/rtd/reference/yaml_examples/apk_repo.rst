.. _cce-apk-repo:

Configure APK repositories
**************************

These examples show how to configure the ``/etc/apk/repositories`` file. For a
full list of keys, refer to the
:ref:`APK configure module <mod_cc_apk_configure>` schema.

Keep the existing ``/etc/apk/repositories`` file unaltered.

.. literalinclude:: ../../../module-docs/cc_apk_configure/example1.yaml
   :language: yaml
   :linenos:

Alpine v3.12
============

Create the repositories file for Alpine v3.12 main and community, using the
default mirror site.

.. literalinclude:: ../../../module-docs/cc_apk_configure/example2.yaml
   :language: yaml
   :linenos:

Alpine Edge
===========

Create the repositories file for Alpine Edge main, community, and testing,
using a specified mirror site and a local repo.

.. literalinclude:: ../../../module-docs/cc_apk_configure/example3.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _APK configure module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apk-configure
