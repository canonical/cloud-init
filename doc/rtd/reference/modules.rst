.. _modules:

Module reference
****************

Deprecation schedule and versions
=================================

Keys can be documented as ``deprecated``, ``new``, or ``changed``.
This allows cloud-init to evolve as requirements change, and to adopt
better practices without maintaining design decisions indefinitely.

Keys marked as ``deprecated`` or ``changed`` may be removed or changed 5
years from the deprecation date. For example, if a key is deprecated in
version ``22.1`` (the first release in 2022) it is scheduled to be removed in
``27.1`` (first release in 2027). Use of deprecated keys may cause warnings in
the logs. If a key's expected value changes, the key will be marked
``changed`` with a date. A 5 year timeline also applies to changed keys.

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
.. datatemplate:yaml:: ../../module-docs/cc_rsyslog/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_runcmd/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_salt_minion/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_scripts_per_boot/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_scripts_per_instance/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_scripts_per_once/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_scripts_user/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_scripts_vendor/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_seed_random/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_set_hostname/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_set_passwords/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_snap/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_spacewalk/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ssh/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ssh_authkey_fingerprints/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ssh_import_id/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_timezone/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ubuntu_drivers/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_ubuntu_pro/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_update_etc_hosts/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_update_hostname/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_users_groups/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_wireguard/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_write_files/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_yum_add_repo/data.yaml
   :template: modules.tmpl
.. datatemplate:yaml:: ../../module-docs/cc_zypper_add_repo/data.yaml
   :template: modules.tmpl
