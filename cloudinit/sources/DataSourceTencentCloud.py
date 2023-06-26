# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import traceback

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import sources, ssh_util, util
from cloudinit.sources import DataSourceEc2 as EC2
from cloudinit.sources import DataSourceHostname

TENCENTCLOUD_PRODUCT = "Tencent Cloud CVM"
LOG = logging.getLogger(__name__)


class DataSourceTencentCloud(EC2.DataSourceEc2):

    metadata_urls = ["http://169.254.0.23", "http://metadata.tencentyun.com"]

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = "2017-09-19"
    extended_metadata_versions: list[str] = []

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceTencentCloud, self).__init__(sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, "TencentCloud")

    def set_config_mod_always(self, mod_name):
        self.set_mod_always(mod_name, "cloud_config_modules")

    def set_mod_always(self, mod_name, stage):
        modules = self.sys_cfg.get(stage, [])
        new_modules = []
        for mod in modules:
            if mod == mod_name:
                new_modules.append([mod_name, "always"])
            else:
                new_modules.append(mod)
        self.cfg[stage] = new_modules

    def add_config_mod_always(self, mod_name):
        modules = self.sys_cfg.get("cloud_config_modules", [])
        modules.append([mod_name, "always"])
        self.cfg["cloud_config_modules"] = modules

    def check_item_change(self, item, value):
        if not value and item != "ssh_key":
            return False
        changed = False
        d_item = {}
        item_path = "/var/lib/cloud/tencentcloud.item"
        try:
            if os.path.exists(item_path):
                with open(item_path, "r") as f:
                    d_item = json.load(f)
                if d_item.get(item) != value:
                    changed = True
            else:
                changed = True
            if changed:
                d_item[item] = value
                with open(item_path, "w") as f:
                    json.dump(d_item, f)
        except Exception as e:
            LOG.debug(str(e))
            LOG.debug(traceback.format_exc())
            changed = True
        LOG.debug("%s changed %s", item, changed)
        return changed

    def del_authorized_keys(self, old_entries, keys):
        to_del = []
        for i in range(0, len(old_entries)):
            ent = old_entries[i]
            if not ent.valid():
                continue
            # Replace those with the same base64
            for k in keys:
                if k.base64 == ent.base64:
                    # Replace it with our better one
                    ent = k
                    to_del.append(k)
            old_entries[i] = ent

        # Now format them back to strings...
        lines = [str(b) for b in old_entries if b not in to_del]

        # Ensure it ends with a newline
        lines.append("")
        return ("\n".join(lines), len(to_del) > 0)

    def del_user_keys(self, keys, username, options=None):
        # Make sure the users .ssh dir is setup accordingly
        (ssh_dir, pwent) = ssh_util.users_ssh_info(username)
        if not os.path.isdir(ssh_dir):
            util.ensure_dir(ssh_dir, mode=0o700)
            util.chownbyid(ssh_dir, pwent.pw_uid, pwent.pw_gid)

        # Turn the 'update' keys given into actual entries
        parser = ssh_util.AuthKeyLineParser()
        key_entries = []
        for k in keys:
            key_entries.append(parser.parse(str(k), options=options))

        # Extract the old and make the new
        (auth_key_fn, auth_key_entries) = ssh_util.extract_authorized_keys(
            username
        )
        with util.SeLinuxGuard(ssh_dir, recursive=True):
            content, to_del = self.del_authorized_keys(
                auth_key_entries, key_entries
            )
            if to_del:
                util.ensure_dir(os.path.dirname(auth_key_fn), mode=0o700)
                util.write_file(auth_key_fn, content, mode=0o600)
                util.chownbyid(auth_key_fn, pwent.pw_uid, pwent.pw_gid)

    def get_data(self):
        self.get_network_metadata = True
        data = super(DataSourceTencentCloud, self).get_data()
        self.cfg = {
            "runcmd": self.metadata.get("runcmd", []),
            "manage_etc_hosts": "template",
            "ntp": self.metadata.get("ntp", {}),
            "unverified_modules": ["ntp"],
            "users": [],
        }
        # password
        passwd = self.metadata.get("password")
        if passwd is not None:
            self.cfg["ssh_pwauth"] = (True,)
            self.cfg["chpasswd"] = {"expire": False, "list": [passwd]}
            ch_passwd = self.check_item_change("passwd", passwd)
            if ch_passwd:
                self.set_config_mod_always("set-passwords")
        # hostname
        hostname = self.get_hostname()
        if hostname is None:
            self.cfg["preserve_hostname"] = True
        ch_hostname = self.check_item_change("hostname", hostname)
        if ch_hostname:
            self.add_config_mod_always("set-hostname")
            self.add_config_mod_always("update_hostname")
            self.add_config_mod_always("update_etc_hosts")
            self.set_config_mod_always("runcmd")
        # ssh key
        ubuntu = self.distro.name == "ubuntu"
        username = "ubuntu" if ubuntu else "root"
        # disassociated_keys
        # delet key from authorized_keys
        disassociated_ssh_keys = self.get_disassociated_public_ssh_keys()
        ch_disassociated_ssh_key = self.check_item_change(
            "disassociated_ssh_key", disassociated_ssh_keys
        )
        if ch_disassociated_ssh_key:
            self.del_user_keys(disassociated_ssh_keys, username)
        # public_keys
        # append key to authorized_keys
        ssh_key = self.get_public_ssh_keys()
        ch_ssh_key = self.check_item_change("ssh_key", ssh_key)
        if ch_ssh_key:
            self.add_config_mod_always("users-groups")
            self.set_config_mod_always("set-passwords")
            if ssh_key:
                self.cfg["ssh_pwauth"] = False
                users = parse_users_config(
                    self.metadata.get("public-keys", {})
                )
                self.cfg["users"].extend(users)
            else:
                self.cfg["ssh_pwauth"] = True
                self.cfg["users"].append(
                    {
                        "name": username,
                        "lock_passwd": False,
                    }
                )

        return data

    def get_config_obj(self):
        return self.cfg

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        hostname = self.metadata.get("hostname")
        is_default = False
        if hostname is None:
            hostname = "localhost.localdomain"
            is_default = True
        return DataSourceHostname(hostname, is_default)

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get("public-keys", {}))

    def get_disassociated_public_ssh_keys(self):
        return parse_public_keys(
            self.metadata.get("disassociated-public-keys", {})
        )

    def _get_cloud_name(self):
        return "TencentCloud"

    @property
    def cloud_platform(self):
        """
        todo:
        1, 通过DMI数据判断是否腾讯云平台。DMI数据：/sys/class/dmi/id/product_name
        2, 添加EC2.Platforms.TENCENTCLOUD
        """
        return "TencentCloud"


def _is_tencentcloud():
    return dmi.read_dmi_data("system-product-name") == TENCENTCLOUD_PRODUCT


def parse_public_keys(public_keys):
    keys = []
    for _key_id, key_body in public_keys.items():
        if isinstance(key_body, str):
            keys.append(key_body.strip())
        elif isinstance(key_body, list):
            keys.extend(key_body)
        elif isinstance(key_body, dict):
            key = key_body.get("openssh-key", [])
            if isinstance(key, str):
                keys.append(key.strip())
            elif isinstance(key, list):
                keys.extend(key)
    return keys


def clean_authorized_keys(user_name):
    if user_name == "root":
        ssh_key_path = "/root/.ssh/authorized_keys"
    else:
        ssh_key_path = "/home/%s/.ssh/authorized_keys" % user_name
    if os.path.exists(ssh_key_path):
        os.remove(ssh_key_path)


def parse_users_config(public_keys):
    users = {}
    for _k_id, k_body in public_keys.items():
        if isinstance(k_body, dict):
            name = k_body["user"]
            if users.get(name):
                users[name]["ssh_authorized_keys"].append(
                    k_body.get("openssh-key", "")
                )
            else:
                users[name] = {
                    "name": name,
                    "ssh_authorized_keys": [k_body.get("openssh-key", "")],
                }
    return [t for _, t in users.items()]


# Used to match classes to dependencies
datasources = [
    (DataSourceTencentCloud, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
