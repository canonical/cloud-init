#!/usr/bin/python3

import sys
import os

# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_runcmd

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers

from cloudinit.sources import DataSourceNoCloud

from cloudinit import log as logging
cfg = {
    'datasource': {'NoCloud': {'fs_label': None, 'instance-id': 'b302d9a1-ea2a-4f1f-930a-c0d0aa1dc5cf'}},
    'runcmd': ["echo 'Instance has been configured by cloud-init.' | wall"],
    'instance-id': {'default': 'iid-datasource-none'},
}

LOG = logging.getLogger(__name__)

logging.setupLogging(cfg)

def _get_cloud(distro):
    paths = helpers.Paths(cfg, {'datasource': {'NoCloud': {'fs_label': None, 'instance-id': 'b302d9a1-ea2a-4f1f-930a-c0d0aa1dc5cf'}}})
    cls = distros.fetch(distro)
    d = cls(distro, {}, paths)
    ds = DataSourceNoCloud.DataSourceNoCloud({'NoCloud': {'fs_label': None, 'instance-id': 'b302d9a1-ea2a-4f1f-930a-c0d0aa1dc5cf'}}, d, paths)
    cc = cloud.Cloud(ds, paths, cfg, d, None)
    return cc


#cfg = {
#    'instance-id': {'default': 'iid-datasource-none'},
#    'datasource': {'NoCloud': {'fs_label': None}, 'instance-id': 'b302d9a1-ea2a-4f1f-930a-c0d0aa1dc5cf'},
#    'runcmd': ["echo 'Instance has been configured by cloud-init.' | wall"],
#}
cc = _get_cloud('aix')

cc_runcmd.handle('cc_runcmd', cfg, cc, LOG, [])
