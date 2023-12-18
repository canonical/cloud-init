#!/usr/bin/python3

import sys
import os


# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_resolv_conf

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers

from cloudinit.sources import DataSourceNoCloud

from cloudinit import log as logging

LOG = logging.getLogger(__name__)

cfg = {
    'datasource': {'NoCloud': {'fs_label': None}}
}

logging.setupLogging(cfg)

def _get_cloud(distro):
    paths = helpers.Paths({})
    cls = distros.fetch(distro)
    d = cls(distro, {}, paths)
    ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
    cc = cloud.Cloud(ds, paths, {}, d, None)
    return cc

cfg = {
    'manage_resolv_conf': True,
    'resolv_conf': {
        'nameservers': ['9.3.1.200'],
        'domain': 'aus.stglabs.ibm.com',
        'searchdomains': ['aus.stglabs.ibm.com']
    }
}

cc = _get_cloud('aix')

cc_resolv_conf.handle('cc_resolv_conf', cfg, cc, LOG, [])
