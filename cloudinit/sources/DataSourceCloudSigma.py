# Copyright (C) 2014 CloudSigma
#
# Author: Kiril Vladimiroff <kiril.vladimiroff@cloudsigma.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from base64 import b64decode
import re

from cloudinit.cs_utils import Cepko

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)


class DataSourceCloudSigma(sources.DataSource):
    """
    Uses cepko in order to gather the server context from the VM.

    For more information about CloudSigma's Server Context:
    http://cloudsigma-docs.readthedocs.org/en/latest/server_context.html
    """

    dsname = 'CloudSigma'

    def __init__(self, sys_cfg, distro, paths):
        self.cepko = Cepko()
        self.ssh_public_key = ''
        sources.DataSource.__init__(self, sys_cfg, distro, paths)

    def is_running_in_cloudsigma(self):
        """
        Uses dmi data to detect if this instance of cloud-init is running
        in the CloudSigma's infrastructure.
        """

        LOG.debug("determining hypervisor product name via dmi data")
        sys_product_name = util.read_dmi_data("system-product-name")
        if not sys_product_name:
            LOG.debug("system-product-name not available in dmi data")
            return False
        else:
            LOG.debug("detected hypervisor as %s", sys_product_name)
            return 'cloudsigma' in sys_product_name.lower()

        LOG.warning("failed to query dmi data for system product name")
        return False

    def _get_data(self):
        """
        Metadata is the whole server context and /meta/cloud-config is used
        as userdata.
        """
        dsmode = None
        if not self.is_running_in_cloudsigma():
            return False

        try:
            server_context = self.cepko.all().result
            server_meta = server_context['meta']
        except Exception:
            # TODO: check for explicit "config on", and then warn
            # but since no explicit config is available now, just debug.
            LOG.debug("CloudSigma: Unable to read from serial port")
            return False

        self.dsmode = self._determine_dsmode(
            [server_meta.get('cloudinit-dsmode')])
        if dsmode == sources.DSMODE_DISABLED:
            return False

        base64_fields = server_meta.get('base64_fields', '').split(',')
        self.userdata_raw = server_meta.get('cloudinit-user-data', "")
        if 'cloudinit-user-data' in base64_fields:
            self.userdata_raw = b64decode(self.userdata_raw)
        if 'cloudinit' in server_context.get('vendor_data', {}):
            self.vendordata_raw = server_context["vendor_data"]["cloudinit"]

        self.metadata = server_context
        self.ssh_public_key = server_meta['ssh_public_key']

        return True

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        """
        Cleans up and uses the server's name if the latter is set. Otherwise
        the first part from uuid is being used.
        """
        if re.match(r'^[A-Za-z0-9 -_\.]+$', self.metadata['name']):
            return self.metadata['name'][:61]
        else:
            return self.metadata['uuid'].split('-')[0]

    def get_public_ssh_keys(self):
        return [self.ssh_public_key]

    def get_instance_id(self):
        return self.metadata['uuid']


# Legacy: Must be present in case we load an old pkl object
DataSourceCloudSigmaNet = DataSourceCloudSigma

# Used to match classes to dependencies. Since this datasource uses the serial
# port network is not really required, so it's okay to load without it, too.
datasources = [
    (DataSourceCloudSigma, (sources.DEP_FILESYSTEM, )),
]


def get_datasource_list(depends):
    """
    Return a list of data sources that match this set of dependencies
    """
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
