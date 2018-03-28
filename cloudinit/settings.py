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
CLOUD_CONFIG = '/etc/cloud/cloud.cfg'

RUN_CLOUD_CONFIG = '/run/cloud-init/cloud.cfg'

# What u get if no config is provided
CFG_BUILTIN = {
    'datasource_list': [
        'NoCloud',
        'ConfigDrive',
        'OpenNebula',
        'DigitalOcean',
        'Azure',
        'AltCloud',
        'OVF',
        'MAAS',
        'GCE',
        'OpenStack',
        'AliYun',
        'Ec2',
        'CloudSigma',
        'CloudStack',
        'SmartOS',
        'Bigstep',
        'Scaleway',
        'Hetzner',
        'IBMCloud',
        # At the end to act as a 'catch' when none of the above work...
        'None',
    ],
    'def_log_file': '/var/log/cloud-init.log',
    'log_cfgs': [],
    'syslog_fix_perms': ['syslog:adm', 'root:adm', 'root:wheel'],
    'system_info': {
        'paths': {
            'cloud_dir': '/var/lib/cloud',
            'templates_dir': '/etc/cloud/templates/',
        },
        'distro': 'ubuntu',
        'network': {'renderers': None},
    },
    'vendor_data': {'enabled': True, 'prefix': []},
}

# Valid frequencies of handlers/modules
PER_INSTANCE = "once-per-instance"
PER_ALWAYS = "always"
PER_ONCE = "once"

# Used to sanity check incoming handlers/modules frequencies
FREQUENCIES = [PER_INSTANCE, PER_ALWAYS, PER_ONCE]

# vi: ts=4 expandtab
