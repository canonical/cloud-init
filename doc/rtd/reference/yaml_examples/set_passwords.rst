.. _cce-set-passwords:

User passwords
**************

For a full list of keys, refer to the
:ref:`set passwords module <mod_cc_set_passwords>` schema.

Set default password
====================

This example sets a default password that would need to be changed by the
user the first time they log in.

.. literalinclude:: ../../../module-docs/cc_set_passwords/example1.yaml
   :language: yaml
   :linenos:

Multi-user configuration
========================

This example does several things:

- Disables SSH password authentication
- Doesn't require users to change their passwords on next login
- Sets the password for ``user1`` to be ``'password1'`` (OS does hashing)
- Sets the password for ``user2`` to a pre-hashed password
- Sets the password for ``user3`` to be a randomly generated password, which
  will be written to the system console

.. literalinclude:: ../../../module-docs/cc_set_passwords/example2.yaml
   :language: yaml
   :linenos:

