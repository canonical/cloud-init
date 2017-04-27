# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

import os
import time

LOG = logging.getLogger()

WARNINGS = {
    'non_ec2_md': """
This system is using the EC2 Metadata Service, but does not appear to
be running on Amazon EC2 or one of cloud-init's known platforms that
provide a EC2 Metadata service. In the future, cloud-init may stop
reading metadata from the EC2 Metadata Service unless the platform can
be identified.

If you are seeing this message, please file a bug against
cloud-init at
   https://bugs.launchpad.net/cloud-init/+filebug?field.tags=dsid
Make sure to include the cloud provider your instance is
running on.

For more information see
  https://bugs.launchpad.net/bugs/1660385

After you have filed a bug, you can disable this warning by
launching your instance with the cloud-config below, or
putting that content into
   /etc/cloud/cloud.cfg.d/99-ec2-datasource.cfg

#cloud-config
datasource:
 Ec2:
  strict_id: false""",
    'dsid_missing_source': """
A new feature in cloud-init identified possible datasources for
this system as:
  {dslist}
However, the datasource used was: {source}

In the future, cloud-init will only attempt to use datasources that
are identified or specifically configured.
For more information see
  https://bugs.launchpad.net/bugs/1669675

If you are seeing this message, please file a bug against
cloud-init at
   https://bugs.launchpad.net/cloud-init/+filebug?field.tags=dsid
Make sure to include the cloud provider your instance is
running on.

After you have filed a bug, you can disable this warning by launching
your instance with the cloud-config below, or putting that content
into /etc/cloud/cloud.cfg.d/99-warnings.cfg

#cloud-config
warnings:
  dsid_missing_source: off""",
}


def _get_warn_dir(cfg):
    paths = helpers.Paths(
        path_cfgs=cfg.get('system_info', {}).get('paths', {}))
    return paths.get_ipath_cur('warnings')


def _load_warn_cfg(cfg, name, mode=True, sleep=None):
    # parse cfg['warnings']['name'] returning boolean, sleep
    # expected value is form of:
    #   (on|off|true|false|sleep)[,sleeptime]
    # boolean True == on, False == off
    default = (mode, sleep)
    if not cfg or not isinstance(cfg, dict):
        return default

    ncfg = util.get_cfg_by_path(cfg, ('warnings', name))
    if ncfg is None:
        return default

    if ncfg in ("on", "true", True):
        return True, None

    if ncfg in ("off", "false", False):
        return False, None

    mode, _, csleep = ncfg.partition(",")
    if mode != "sleep":
        return default

    if csleep:
        try:
            sleep = int(csleep)
        except ValueError:
            return default

    return True, sleep


def show_warning(name, cfg=None, sleep=None, mode=True, **kwargs):
    # kwargs are used for .format of the message.
    # sleep and mode are default values used if
    #   cfg['warnings']['name'] is not present.
    if cfg is None:
        cfg = {}

    mode, sleep = _load_warn_cfg(cfg, name, mode=mode, sleep=sleep)
    if not mode:
        return

    msg = WARNINGS[name].format(**kwargs)
    msgwidth = 70
    linewidth = msgwidth + 4

    fmt = "# %%-%ds #" % msgwidth
    topline = "*" * linewidth + "\n"
    fmtlines = []
    for line in msg.strip("\n").splitlines():
        fmtlines.append(fmt % line)

    closeline = topline
    if sleep:
        sleepmsg = "  [sleeping for %d seconds]  " % sleep
        closeline = sleepmsg.center(linewidth, "*") + "\n"

    util.write_file(
        os.path.join(_get_warn_dir(cfg), name),
        topline + "\n".join(fmtlines) + "\n" + topline)

    LOG.warning(topline + "\n".join(fmtlines) + "\n" + closeline)

    if sleep:
        LOG.debug("sleeping %d seconds for warning '%s'", sleep, name)
        time.sleep(sleep)

# vi: ts=4 expandtab
