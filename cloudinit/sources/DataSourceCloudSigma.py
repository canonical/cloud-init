# vi: ts=4 expandtab
#
#    Copyright (C) 2014 CloudSigma
#
#    Author: Kiril Vladimiroff <kiril.vladimiroff@cloudsigma.com>
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
from base64 import b64decode
import os
import re

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util
from cloudinit.cs_utils import Cepko

LOG = logging.getLogger(__name__)

VALID_DSMODES = ("local", "net", "disabled")


class DataSourceCloudSigma(sources.DataSource):
    """
    Uses cepko in order to gather the server context from the VM.

    For more information about CloudSigma's Server Context:
    http://cloudsigma-docs.readthedocs.org/en/latest/server_context.html
    """
    def __init__(self, sys_cfg, distro, paths):
        self.dsmode = 'local'
        self.cepko = Cepko()
        self.ssh_public_key = ''
        sources.DataSource.__init__(self, sys_cfg, distro, paths)

    def is_running_in_cloudsigma(self):
        """
        Uses dmidecode to detect if this instance of cloud-init is running
        in the CloudSigma's infrastructure.
        """
        uname_arch = os.uname()[4]
        if uname_arch.startswith("arm") or uname_arch == "aarch64":
            # Disabling because dmidecode in CMD_DMI_SYSTEM crashes kvm process
            LOG.debug("Disabling CloudSigma datasource on arm (LP: #1243287)")
            return False

        dmidecode_path = util.which('dmidecode')
        if not dmidecode_path:
            return False

        LOG.debug("Determining hypervisor product name via dmidecode")
        try:
            cmd = [dmidecode_path, "--string", "system-product-name"]
            system_product_name, _ = util.subp(cmd)
            return 'cloudsigma' in system_product_name.lower()
        except:
            LOG.warn("Failed to get hypervisor product name via dmidecode")

        return False

    def get_data(self):
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
        except:
            # TODO: check for explicit "config on", and then warn
            # but since no explicit config is available now, just debug.
            LOG.debug("CloudSigma: Unable to read from serial port")
            return False

        dsmode = server_meta.get('cloudinit-dsmode', self.dsmode)
        if dsmode not in VALID_DSMODES:
            LOG.warn("Invalid dsmode %s, assuming default of 'net'", dsmode)
            dsmode = 'net'
        if dsmode == "disabled" or dsmode != self.dsmode:
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

    def get_hostname(self, fqdn=False, resolve_ip=False):
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


class DataSourceCloudSigmaNet(DataSourceCloudSigma):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceCloudSigma.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'net'


# Used to match classes to dependencies. Since this datasource uses the serial
# port network is not really required, so it's okay to load without it, too.
datasources = [
    (DataSourceCloudSigma, (sources.DEP_FILESYSTEM)),
    (DataSourceCloudSigmaNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


def get_datasource_list(depends):
    """
    Return a list of data sources that match this set of dependencies
    """
    return sources.list_from_depends(depends, datasources)
