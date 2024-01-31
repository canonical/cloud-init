.. _modules:

Module reference
****************

Deprecation schedule and versions
---------------------------------
Keys may be documented as ``deprecated``, ``new``, or ``changed``.
This allows cloud-init to evolve as requirements change, and to adopt
better practices without maintaining design decisions indefinitely.

Keys that have been marked as deprecated or changed may be removed or
changed 5 years from the date of deprecation. For example, a key that is
deprecated in version ``22.1`` (which is the first release in 2022) is
scheduled to be removed in ``27.1`` (first release in 2027). Use of
deprecated keys may cause warnings in the logs. In the case that a
key's expected value changes, the key will be marked ``changed`` with a
date. A 5 year timeline may also be expected for changed keys.

.. automodule:: cloudinit.config.cc_ansible
.. automodule:: cloudinit.config.cc_apk_configure
.. automodule:: cloudinit.config.cc_apt_configure
.. automodule:: cloudinit.config.cc_apt_pipelining
.. automodule:: cloudinit.config.cc_bootcmd
.. automodule:: cloudinit.config.cc_byobu
.. automodule:: cloudinit.config.cc_ca_certs
.. automodule:: cloudinit.config.cc_chef
.. automodule:: cloudinit.config.cc_disable_ec2_metadata

.. _mod-disk_setup:

.. automodule:: cloudinit.config.cc_disk_setup
.. automodule:: cloudinit.config.cc_fan
.. automodule:: cloudinit.config.cc_final_message
.. automodule:: cloudinit.config.cc_growpart
.. automodule:: cloudinit.config.cc_grub_dpkg
.. automodule:: cloudinit.config.cc_install_hotplug
.. automodule:: cloudinit.config.cc_keyboard
.. automodule:: cloudinit.config.cc_keys_to_console
.. automodule:: cloudinit.config.cc_landscape
.. automodule:: cloudinit.config.cc_locale
.. automodule:: cloudinit.config.cc_lxd
.. automodule:: cloudinit.config.cc_mcollective
.. automodule:: cloudinit.config.cc_mounts

.. _mod-ntp:

.. automodule:: cloudinit.config.cc_ntp
.. automodule:: cloudinit.config.cc_package_update_upgrade_install
.. automodule:: cloudinit.config.cc_phone_home
.. automodule:: cloudinit.config.cc_power_state_change
.. automodule:: cloudinit.config.cc_puppet
.. automodule:: cloudinit.config.cc_resizefs
.. automodule:: cloudinit.config.cc_resolv_conf
.. automodule:: cloudinit.config.cc_rh_subscription

.. _mod-rsyslog:

.. automodule:: cloudinit.config.cc_rsyslog

.. _mod-runcmd:

.. automodule:: cloudinit.config.cc_runcmd
.. automodule:: cloudinit.config.cc_salt_minion
.. automodule:: cloudinit.config.cc_scripts_per_boot
.. automodule:: cloudinit.config.cc_scripts_per_instance
.. automodule:: cloudinit.config.cc_scripts_per_once
.. automodule:: cloudinit.config.cc_scripts_user
.. automodule:: cloudinit.config.cc_scripts_vendor
.. automodule:: cloudinit.config.cc_seed_random
.. automodule:: cloudinit.config.cc_set_hostname

.. _mod-set_passwords:

.. automodule:: cloudinit.config.cc_set_passwords
.. automodule:: cloudinit.config.cc_snap
.. automodule:: cloudinit.config.cc_spacewalk
.. automodule:: cloudinit.config.cc_ssh
.. automodule:: cloudinit.config.cc_ssh_authkey_fingerprints
.. automodule:: cloudinit.config.cc_ssh_import_id
.. automodule:: cloudinit.config.cc_timezone
.. automodule:: cloudinit.config.cc_ubuntu_advantage
.. automodule:: cloudinit.config.cc_ubuntu_drivers
.. automodule:: cloudinit.config.cc_update_etc_hosts
.. automodule:: cloudinit.config.cc_update_hostname

.. _mod-users_groups:

.. automodule:: cloudinit.config.cc_users_groups
.. automodule:: cloudinit.config.cc_wireguard
.. automodule:: cloudinit.config.cc_write_files
.. automodule:: cloudinit.config.cc_yum_add_repo
.. automodule:: cloudinit.config.cc_zypper_add_repo
