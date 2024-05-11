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

.. datatemplate:yaml:: ../../module-docs/cc_ansible/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_apk_configure/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_apt_configure/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_apt_pipelining/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_bootcmd/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_byobu/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ca_certs/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_chef/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_disable_ec2_metadata/data.yaml
   :template: modules.tmpl

.. _mod-disk_setup:

.. datatemplate:yaml:: ../../module-docs/cc_disk_setup/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_fan/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_final_message/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_growpart/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_grub_dpkg/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_install_hotplug/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_keyboard/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_keys_to_console/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_landscape/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_locale/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_lxd/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_mcollective/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_mounts/data.yaml
   :template: modules.tmpl

.. _mod-ntp:

.. datatemplate:yaml:: ../../module-docs/cc_ntp/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_package_update_upgrade_install/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_phone_home/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_power_state_change/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_puppet/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_resizefs/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_resolv_conf/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_rh_subscription/data.yaml
   :template: modules.tmpl

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

.. _mod-set_hostname:

.. automodule:: cloudinit.config.cc_set_hostname

.. _mod-set_passwords:

.. automodule:: cloudinit.config.cc_set_passwords
.. automodule:: cloudinit.config.cc_snap
.. automodule:: cloudinit.config.cc_spacewalk
.. automodule:: cloudinit.config.cc_ssh
.. automodule:: cloudinit.config.cc_ssh_authkey_fingerprints
.. automodule:: cloudinit.config.cc_ssh_import_id
.. automodule:: cloudinit.config.cc_timezone
.. automodule:: cloudinit.config.cc_ubuntu_drivers
.. automodule:: cloudinit.config.cc_ubuntu_pro
.. automodule:: cloudinit.config.cc_update_etc_hosts
.. automodule:: cloudinit.config.cc_update_hostname

.. _mod-users_groups:

.. automodule:: cloudinit.config.cc_users_groups
.. automodule:: cloudinit.config.cc_wireguard

.. _mod-write_files:

.. automodule:: cloudinit.config.cc_write_files
.. automodule:: cloudinit.config.cc_yum_add_repo
.. automodule:: cloudinit.config.cc_zypper_add_repo
