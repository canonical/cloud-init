# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

CFG_ENV_NAME = "CLOUD_CFG"
CLOUD_CONFIG = '/etc/cloud/cloud.cfg'
OLD_CLOUD_CONFIG = '/etc/ec2-init/ec2-config.cfg'

CFG_BUILTIN = {
    'datasource_list': [
        'NoCloud',
        'ConfigDrive',
        'OVF',
        'MAAS',
        'Ec2',
        'CloudStack'
    ],
    'def_log_file': '/var/log/cloud-init.log',
    'log_cfgs': [],
    'syslog_fix_perms': 'syslog:adm',
    'system_info': {
        'paths': {
            'cloud_dir': '/var/lib/cloud',
            'templates_dir': '/etc/cloud/templates/',
        }, 
        'distro': 'ubuntu',
    },
}

PER_INSTANCE = "once-per-instance"
PER_ALWAYS = "always"
PER_ONCE = "once"

