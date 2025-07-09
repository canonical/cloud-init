Security Hardening
******************

Cloud-init's use case is automating cloud instance initialization, with support
across distributions and platforms. There is a myriad of ways to harden this
space.

Follow the security hardening guidelines provided by the OSes and cloud
platforms that your cloud-init configuration is targeting.

No plain text passwords
=======================

While creating users with the
:ref:`Users and Groups module <mod_cc_users_groups>`, do not use the
`user.plain_text_passwd` key with its associated value as plain text.
As anyone with access to the configuration might have access to the password.

