# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Canonical Ltd.
#
#    Author: Ben Howard <ben.howard@canonical.com>
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
#
#
#    Datasource for provisioning on SmartOS. This works on Joyent
#        and public/private Clouds using SmartOS.
#
#    SmartOS hosts use a serial console (/dev/ttyS1) on Linux Guests.
#        The meta-data is transmitted via key/value pairs made by
#        requests on the console. For example, to get the hostname, you
#        would send "GET hostname" on /dev/ttyS1.
#


import os
import os.path
import serial
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util


DEF_TTY_LOC = '/dev/ttyS1'
TTY_LOC = None
LOG = logging.getLogger(__name__)


class DataSourceSmartOS(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'sdc')
        self.seed = None
        self.is_smartdc = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        md = {}
        ud = ""

        TTY_LOC = self.sys_cfg.get("serial_device", DEF_TTY_LOC)
        if not os.path.exists(TTY_LOC):
            LOG.debug("Host does not appear to be on SmartOS")
            return False
        self.seed = TTY_LOC

        system_uuid, system_type = dmi_data()
        if 'smartdc' not in system_type.lower():
            LOG.debug("Host is not on SmartOS")
            return False
        self.is_smartdc = True

        hostname = query_data("hostname", strip=True)
        if not hostname:
            hostname = system_uuid

        md['local-hostname'] = hostname
        md['instance-id'] = system_uuid
        md['public-keys'] = query_data("root_authorized_keys", strip=True)
        md['user-script'] = query_data("user-script")
        md['user-data'] = query_data("user-script")
        md['iptables_disable'] = query_data("disable_iptables_flag",
                                            strip=True)
        md['motd_sys_info'] = query_data("enable_motd_sys_info", strip=True)

        if md['user-data']:
            ud = md['user-data']
        else:
            ud = md['user-script']

        self.metadata = md
        self.userdata_raw = ud
        return True

    def get_instance_id(self):
        return self.metadata['instance-id']


def get_serial():
    """This is replaced in unit testing, allowing us to replace
        serial.Serial with a mocked class

        The timeout value of 60 seconds should never be hit. The value
        is taken from SmartOS own provisioning tools. Since we are reading
        each line individually up until the single ".", the transfer is
        usually very fast (i.e. microseconds) to get the response.
    """
    if not TTY_LOC:
        raise AttributeError("TTY_LOC value is not set")

    _ret = serial.Serial(TTY_LOC, timeout=60)
    if not _ret.isOpen():
        raise SystemError("Unable to open %s" % TTY_LOC)

    return _ret



def query_data(noun, strip=False):
    """Makes a request to via the serial console via "GET <NOUN>"

        In the response, the first line is the status, while subsequent lines
        are is the value. A blank line with a "." is used to indicate end of
        response.
    """

    if not noun:
        return False

    ser = get_serial()
    ser.write("GET %s\n" % noun.rstrip())
    status = str(ser.readline()).rstrip()
    response = []
    eom_found = False

    if 'SUCCESS' not in status:
        ser.close()
        return None

    while not eom_found:
        m = ser.readline()
        if m.rstrip() == ".":
            eom_found = True
        else:
            response.append(m)

    ser.close()
    if not strip:
        return "".join(response)
    else:
        return "".join(response).rstrip()

    return None


def dmi_data():
    sys_uuid, sys_type = None, None
    dmidecode_path = util.which('dmidecode')
    if not dmidecode_path:
        return False

    sys_uuid_cmd = [dmidecode_path, "-s", "system-uuid"]
    try:
        LOG.debug("Getting hostname from dmidecode")
        (sys_uuid, _err) = util.subp(sys_uuid_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed to get system UUID", e)

    sys_type_cmd = [dmidecode_path, "-s", "system-product-name"]
    try:
        LOG.debug("Determining hypervisor product name via dmidecode")
        (sys_type, _err) = util.subp(sys_type_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed to get system UUID", e)

    return sys_uuid.lower(), sys_type


# Used to match classes to dependencies
datasources = [
    (DataSourceSmartOS, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
