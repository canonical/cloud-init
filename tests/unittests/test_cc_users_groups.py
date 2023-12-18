#!/usr/bin/python3

import sys
import os
# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_users_groups

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers

from cloudinit.sources import DataSourceNoCloud

from cloudinit import log as logging
cfg = {
    'datasource': {'NoCloud': {'fs_label': None}}
}

LOG = logging.getLogger(__name__)

logging.setupLogging(cfg)

def _get_cloud(distro):
    paths = helpers.Paths({})
    cls = distros.fetch(distro)
    d = cls(distro, {}, paths)
    ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
    cc = cloud.Cloud(ds, paths, {}, d, None)
    return cc


cfg = {
    'users': [{
        'ssh-authorized-keys': [
             'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCYWbhUTfKRfgtTUU1/u2KVNXkj1cWoBCW730W15x3lXZfgdKIjxYXzbSOrWJamj9CFOzIcy3CZ4CqAaIDb37SGY0mhfcPtgL1R2DVCsppbkv/V34omxGn2G//SK6GtirMhN4d6ze4PSDqvd6sotEDK6Z7TwPuUhxGh7Z2T/0OC98DSYHiUmshBQbml4qynnsl74ybhXzm4e/pk3HF9WZnAQEOxQxWnWLAOtnpllgNB93S6/AOiMXAObUq1vaUPOZKgBsmXB7heYLveU0bXucYODzrYGwL5gYWGsUMvukGV8DgCySym3VivOe0gnhX/FN6vZ8589y6dZvRlMXtQZ/bgGYWAMiNyusafYFiUhBlrT+K5H37kr4F9p0Ytul/MC800c9txlGiqoKSBhn6dDBL9mC7hnHQgqXP3ZOnWDWvkOqySTigu/UTtf0n5KHkD0q5BwDkXgRdQsCF9Ov3bJTnSr+H3r6znXnhxtMkCyQzFCZ8h5XdKHrIABVm65yodmKE= root@idevp9-lp2',
        ],
        'shell': '/bin/ksh',
        'name': 'demo',
        'groups': 'group2',
        'sudo': ['ALL=(ALL) NOPASSWD:ALL'],
        'runcmd': ['touch /tmp/test.txt']}],
    'groups': [
        'group1',
        {'group2': ['demo']}
    ],
}
cc = _get_cloud('aix')

# Check /etc/security/login.cfg to see if the 'shell' such as /bin/bash is a valid option
#cc_str= str(cc_users_groups)
#cc_users_groups_byte= cc_str.encode()
#print(type(cc_users_groups_byte))
cc_users_groups.handle('cc_users_groups', cfg, cc, LOG, [])
