# Copyright (C) 2018 Warsaw Data Center
#
# Author: Malwina Leis <m.leis@rootbox.com>
# Author: Grzegorz Brzeski <gregory@rootbox.io>
# Author: Adam Dobrawy <a.dobrawy@hyperone.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""
This file contains code used to gather the user data passed to an
instance on rootbox / hyperone cloud platforms
"""
import errno
import os
import os.path
import typing
from ipaddress import IPv4Address

from cloudinit import log as logging
from cloudinit import sources, subp, util
from cloudinit.event import EventScope, EventType

LOG = logging.getLogger(__name__)
ETC_HOSTS = "/etc/hosts"


def get_manage_etc_hosts():
    hosts = util.load_file(ETC_HOSTS, quiet=True)
    if hosts:
        LOG.debug("/etc/hosts exists - setting manage_etc_hosts to False")
        return False
    LOG.debug("/etc/hosts does not exists - setting manage_etc_hosts to True")
    return True


def increment_ip(addr, inc: int) -> str:
    return str(IPv4Address(int(IPv4Address(addr)) + inc))


def get_three_ips(addr) -> typing.List[str]:
    """Return a list of 3 IP addresses: [addr, addr + 2, addr + 3]

    @param addr: an object that is passed to IPvAddress
    @return: list of strings
    """
    return [
        addr,
        increment_ip(addr, 2),
        increment_ip(addr, 3),
    ]


def _sub_arp(cmd):
    """
    Uses the preferred cloud-init subprocess def of subp.subp
    and runs arping.  Breaking this to a separate function
    for later use in mocking and unittests
    """
    return subp.subp(["arping"] + cmd)


def gratuitous_arp(items, distro):
    source_param = "-S"
    if distro.name in ["fedora", "centos", "rhel"]:
        source_param = "-s"
    for item in items:
        try:
            _sub_arp(
                ["-c", "2", source_param, item["source"], item["destination"]]
            )
        except subp.ProcessExecutionError as error:
            # warning, because the system is able to function properly
            # despite no success - some ARP table may be waiting for
            # expiration, but the system may continue
            LOG.warning(
                'Failed to arping from "%s" to "%s": %s',
                item["source"],
                item["destination"],
                error,
            )


def get_md():
    """Returns False (not found or error) or a dictionary with metadata."""
    devices = set(
        util.find_devs_with("LABEL=CLOUDMD")
        + util.find_devs_with("LABEL=cloudmd")
    )
    if not devices:
        return False
    for device in devices:
        try:
            rbx_data = util.mount_cb(
                device=device,
                callback=read_user_data_callback,
                mtype=["vfat", "fat", "msdosfs"],
            )
            if rbx_data:
                return rbx_data
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        except util.MountFailedError:
            util.logexc(
                LOG, "Failed to mount %s when looking for user data", device
            )

    LOG.debug(
        "Did not find RbxCloud data, searched devices: %s", ",".join(devices)
    )
    return False


def generate_network_config(netadps):
    """Generate network configuration

    @param netadps: A list of network adapter settings

    @returns: A dict containing network config
    """
    return {
        "version": 1,
        "config": [
            {
                "type": "physical",
                "name": "eth{}".format(str(i)),
                "mac_address": netadp["macaddress"].lower(),
                "subnets": [
                    {
                        "type": "static",
                        "address": ip["address"],
                        "netmask": netadp["network"]["netmask"],
                        "control": "auto",
                        "gateway": netadp["network"]["gateway"],
                        "dns_nameservers": netadp["network"]["dns"][
                            "nameservers"
                        ],
                    }
                    for ip in netadp["ip"]
                ],
            }
            for i, netadp in enumerate(netadps)
        ],
    }


def read_user_data_callback(mount_dir):
    """This callback will be applied by util.mount_cb() on the mounted
    drive.

    @param mount_dir: String representing path of directory where mounted drive
    is available

    @returns: A dict containing userdata, metadata and cfg based on metadata.
    """
    meta_data = util.load_json(
        text=util.load_file(
            fname=os.path.join(mount_dir, "cloud.json"), decode=False
        )
    )
    user_data = util.load_file(
        fname=os.path.join(mount_dir, "user.data"), quiet=True
    )
    if "vm" not in meta_data or "netadp" not in meta_data:
        util.logexc(LOG, "Failed to load metadata. Invalid format.")
        return None
    username = meta_data.get("additionalMetadata", {}).get("username")
    ssh_keys = meta_data.get("additionalMetadata", {}).get("sshKeys", [])

    hash = None
    if meta_data.get("additionalMetadata", {}).get("password"):
        hash = meta_data["additionalMetadata"]["password"]["sha512"]

    network = generate_network_config(meta_data["netadp"])

    data = {
        "userdata": user_data,
        "metadata": {
            "instance-id": meta_data["vm"]["_id"],
            "local-hostname": meta_data["vm"]["name"],
            "public-keys": [],
        },
        "gratuitous_arp": [
            {"source": ip["address"], "destination": target}
            for netadp in meta_data["netadp"]
            for ip in netadp["ip"]
            for target in get_three_ips(netadp["network"]["gateway"])
        ],
        "cfg": {
            "ssh_pwauth": True,
            "disable_root": True,
            "system_info": {
                "default_user": {
                    "name": username,
                    "gecos": username,
                    "sudo": ["ALL=(ALL) NOPASSWD:ALL"],
                    "passwd": hash,
                    "lock_passwd": False,
                    "ssh_authorized_keys": ssh_keys,
                }
            },
            "network_config": network,
            "manage_etc_hosts": get_manage_etc_hosts(),
        },
    }

    LOG.debug("returning DATA object:")
    LOG.debug(data)

    return data


class DataSourceRbxCloud(sources.DataSource):
    dsname = "RbxCloud"
    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
        }
    }

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def _get_data(self):
        """
        Metadata is passed to the launching instance which
        is used to perform instance configuration.
        """
        rbx_data = get_md()
        if rbx_data is False:
            return False
        self.userdata_raw = rbx_data["userdata"]
        self.metadata = rbx_data["metadata"]
        self.gratuitous_arp = rbx_data["gratuitous_arp"]
        self.cfg = rbx_data["cfg"]
        return True

    @property
    def network_config(self):
        return self.cfg["network_config"]

    def get_public_ssh_keys(self):
        return self.metadata["public-keys"]

    def get_userdata_raw(self):
        return self.userdata_raw

    def get_config_obj(self):
        return self.cfg

    def activate(self, cfg, is_new_instance):
        gratuitous_arp(self.gratuitous_arp, self.distro)


# Used to match classes to dependencies
datasources = [
    (DataSourceRbxCloud, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
