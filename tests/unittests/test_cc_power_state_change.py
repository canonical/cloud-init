#!/usr/bin/python3

import sys
import os

# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_power_state_change

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
    'power_state': {'mode': 'reboot', 'message': 'REBOOTING'}

}
cc = _get_cloud('aix')

cc_power_state_change.handle('cc_power_state_change', cfg, cc, LOG, [])

