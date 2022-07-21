import importlib
import re
from typing import Set

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.util import verify_clean_log

activated_modules = {
    # "apk_configure",
    # # "apt_configure",
    # "apt_pipelining",
    # # "bootcmd",
    # "byobu",
    # "ca_certs",
    # # "chef",
    # "debug",
    # "disable_ec2_metadata",
    # # "disk_setup",
    # "fan",
    # "final_message",
    # "growpart",
    # "grub_dpkg",
    # "install_hotplug",
    # "keyboard",
    # "keys_to_console",
    # "landscape",
    # "locale",
    # # "lxd",
    # "mcollective",
    # "migrator",
    # # "mounts",
    # # "ntp",
    # # "package_update_upgrade_install",
    # "phone_home",
    # # "power_state_change",
    # # "puppet",
    # "refresh_rmc_and_interface",
    # "reset_rmc",
    # "resizefs",
    # "resolv_conf",
    # # "rh_subscription",
    # "rightscale_userdata",
    # "rsyslog",
    # "runcmd",
    # "salt_minion",
    # "scripts_per_boot",
    # "scripts_per_instance",
    # "scripts_per_once",
    # "scripts_user",
    # "scripts_vendor",
    # # "seed_random",
    "set_hostname",
    "set_passwords",
    "snap",
    "spacewalk",
    "ssh",
    "ssh_authkey_fingerprints",
    "ssh_import_id",
    "timezone",
    "ubuntu_advantage",
    "ubuntu_autoinstall",
    "ubuntu_drivers",
    "update_etc_hosts",
    "update_hostname",
    "users_groups",
    "write_files",
    "write_files_deferred",
    "yum_add_repo",
    "zypper_add_repo",
}


def get_examples():
    examples = []
    for mod_name in sorted(list(activated_modules)):
        module = importlib.import_module(f"cloudinit.config.cc_{mod_name}")
        for i, example in enumerate(module.meta.get("examples", [])):
            examples.append(
                pytest.param(mod_name, example, id=f"{mod_name}_example_{i}")
            )
    return examples


def get_not_activated_modules(log_content: str) -> Set[str]:
    match = re.search(
        r"Skipping modules '(.*)' because no applicable config is provided.",
        log_content,
    )
    if not match:
        raise ValueError("`activated_modules` log entry not found.")
    modules = match.group(1)
    return set(map(lambda m: m.strip(), modules.split(", ")))


# @pytest.mark.adhoc
@pytest.mark.ci
@pytest.mark.parametrize("mod_name, example", get_examples())
def test_examples(mod_name, example, session_cloud: IntegrationCloud):
    """Execute the examples given in module's meta-schemas

    Verify that the log is clean (and without deprecated keys) and the module
    was activated.
    """
    user_data = f"#cloud-config\n{example}"
    with session_cloud.launch(
        launch_kwargs={"user_data": user_data}
    ) as instance:
        log_content = instance.read_from_file("/var/log/cloud-init.log")
        not_activated = get_not_activated_modules(log_content)
        assert mod_name not in not_activated, (
            f"{mod_name} was skipped with a cloud-config example:\n"
            f"{example}\n\nNot activated modules: {not_activated}"
        )
        verify_clean_log(log_content, ignore_deprecations=False)
