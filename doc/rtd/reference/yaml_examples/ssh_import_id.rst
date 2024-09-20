.. _cce-SSH-import-ID:

Import SSH ID
*************

This example imports SSH keys from:

- GitHub (``gh:``)
- A public keyserver (in this case, Launchpad, ``lp:``)

Keys are referenced by the username they are associated with on the keyserver.

For a full list of keys, refer to the
:ref:`SSH import ID module <mod_cc_ssh_import_id>` schema. You may also find it
helpful to consult `the manual page`_.

.. literalinclude:: ../../../module-docs/cc_ssh_import_id/example1.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _the manual page: https://manpages.ubuntu.com/manpages/noble/en/man1/ssh-import-id.1.html
