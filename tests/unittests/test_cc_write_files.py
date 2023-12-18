#!/usr/bin/python3

import sys
import os

# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_write_files

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
    'write_files': [{
        'content': 'Here is a line.\nAnother line is here.\n',
        'path': '/tmp/test.txt'
     }],
}
cc = _get_cloud('aix')

cc_write_files.handle('cc_write_files', cfg, cc, LOG, [])
