# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Set and read for determining the cloud config file location
CFG_ENV_NAME = "CLOUD_CFG"

# This is expected to be a yaml formatted file
CLOUD_CONFIG = "/etc/cloud/cloud.cfg"

CLEAN_RUNPARTS_DIR = "/etc/cloud/clean.d"

DEFAULT_RUN_DIR = "/run/cloud-init"

# What u get if no config is provided
CFG_BUILTIN = {
    "datasource_list": [
        "NoCloud",
        "ConfigDrive",
        "LXD",
        "OpenNebula",
        "DigitalOcean",
        "Azure",
        "AltCloud",
        "OVF",
        "MAAS",
        "GCE",
        "OpenStack",
        "AliYun",
        "Vultr",
        "Ec2",
        "CloudSigma",
        "CloudStack",
        "SmartOS",
        "Bigstep",
        "Scaleway",
        "Hetzner",
        "IBMCloud",
        "Oracle",
        "Exoscale",
        "RbxCloud",
        "UpCloud",
        "VMware",
        "NWCS",
        "Akamai",
        "WSL",
        # At the end to act as a 'catch' when none of the above work...
        "None",
    ],
    "def_log_file": "/var/log/cloud-init.log",
    "log_cfgs": [],
    "syslog_fix_perms": ["syslog:adm", "root:adm", "root:wheel", "root:root"],
    "system_info": {
        "paths": {
            "cloud_dir": "/var/lib/cloud",
            "docs_dir": "/usr/share/doc/cloud-init/",
            "templates_dir": "/etc/cloud/templates/",
        },
        "distro": "ubuntu",
        "network": {"renderers": None},
    },
    "vendor_data": {"enabled": True, "prefix": []},
    "vendor_data2": {"enabled": True, "prefix": []},
}

# Valid frequencies of handlers/modules
PER_INSTANCE = "once-per-instance"
PER_ALWAYS = "always"
PER_ONCE = "once"

# Used to sanity check incoming handlers/modules frequencies
FREQUENCIES = [PER_INSTANCE, PER_ALWAYS, PER_ONCE]

HOTPLUG_ENABLED_FILE = "/var/lib/cloud/hotplug.enabled"
