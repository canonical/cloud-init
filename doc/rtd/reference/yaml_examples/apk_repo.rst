.. _cce-apk-repo:

Configure APK repositories
**************************

These examples show how to configure the ``/etc/apk/repositories`` file. For a
full list of keys, refer to the
:ref:`APK configure module <mod_cc_apk_configure>` schema.

Use ``apk.repositories`` for new configurations. The older ``apk_repos``
format remains available for backwards compatibility.

The ``apk.repositories`` list replaces ``/etc/apk/repositories``. Duplicate
repository URLs are written only once, in their first configured order.

When both forms configure repositories, ``apk.repositories`` takes precedence
and cloud-init logs a warning. An ``apk`` section without ``repositories``
falls back to ``apk_repos``. Set ``apk.preserve_repositories`` to ``true`` to
preserve the existing file and override both forms.

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
using a specified mirror site and a custom repository URL.

.. literalinclude:: ../../../module-docs/cc_apk_configure/example3.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _APK configure module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apk-configure
