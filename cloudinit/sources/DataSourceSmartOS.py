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


import base64
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util
import os
import os.path
import serial


LOG = logging.getLogger(__name__)

SMARTOS_ATTRIB_MAP = {
    #Cloud-init Key : (SmartOS Key, Strip line endings)
    'local-hostname': ('hostname', True),
    'public-keys': ('root_authorized_keys', True),
    'user-script': ('user-script', False),
    'user-data': ('user-data', False),
    'iptables_disable': ('iptables_disable', True),
    'motd_sys_info': ('motd_sys_info', True),
    'availability_zone': ('region', True),
}

DS_NAME = 'SmartOS'
DS_CFG_PATH = ['datasource', DS_NAME]
# BUILT-IN DATASOURCE CONFIGURATION
#  The following is the built-in configuration. If the values
#  are not set via the system configuration, then these default
#  will be used:
#    serial_device: which serial device to use for the meta-data
#    seed_timeout: how long to wait on the device
#    no_base64_decode: values which are not base64 encoded and
#            are fetched directly from SmartOS, not meta-data values
#    base64_keys: meta-data keys that are delivered in base64
#    base64_all: with the exclusion of no_base64_decode values,
#            treat all meta-data as base64 encoded
#    disk_setup: describes how to partition the ephemeral drive
#    fs_setup: describes how to format the ephemeral drive
#
BUILTIN_DS_CONFIG = {
    'serial_device': '/dev/ttyS1',
    'seed_timeout': 60,
    'no_base64_decode': ['root_authorized_keys',
                         'motd_sys_info',
                         'iptables_disable'],
    'base64_keys': [],
    'base64_all': False,
    'disk_aliases': {'ephemeral0': '/dev/vdb'},
}

BUILTIN_CLOUD_CONFIG = {
    'disk_setup': {
        'ephemeral0': {'table_type': 'mbr',
                       'layout': False,
                       'overwrite': False}
         },
    'fs_setup': [{'label': 'ephemeral0',
                  'filesystem': 'ext3',
                  'device': 'ephemeral0'}],
}


class DataSourceSmartOS(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.is_smartdc = None

        self.ds_cfg = util.mergemanydict([
            self.ds_cfg,
            util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}),
            BUILTIN_DS_CONFIG])

        self.metadata = {}
        self.cfg = BUILTIN_CLOUD_CONFIG

        self.seed = self.ds_cfg.get("serial_device")
        self.seed_timeout = self.ds_cfg.get("serial_timeout")
        self.smartos_no_base64 = self.ds_cfg.get('no_base64_decode')
        self.b64_keys = self.ds_cfg.get('base64_keys')
        self.b64_all = self.ds_cfg.get('base64_all')

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        md = {}
        ud = ""

        if not os.path.exists(self.seed):
            LOG.debug("Host does not appear to be on SmartOS")
            return False

        dmi_info = dmi_data()
        if dmi_info is False:
            LOG.debug("No dmidata utility found")
            return False

        system_uuid, system_type = dmi_info
        if 'smartdc' not in system_type.lower():
            LOG.debug("Host is not on SmartOS. system_type=%s", system_type)
            return False
        self.is_smartdc = True
        md['instance-id'] = system_uuid

        b64_keys = self.query('base64_keys', strip=True, b64=False)
        if b64_keys is not None:
            self.b64_keys = [k.strip() for k in str(b64_keys).split(',')]

        b64_all = self.query('base64_all', strip=True, b64=False)
        if b64_all is not None:
            self.b64_all = util.is_true(b64_all)

        for ci_noun, attribute in SMARTOS_ATTRIB_MAP.iteritems():
            smartos_noun, strip = attribute
            md[ci_noun] = self.query(smartos_noun, strip=strip)

        if not md['local-hostname']:
            md['local-hostname'] = system_uuid

        ud = None
        if md['user-data']:
            ud = md['user-data']
        elif md['user-script']:
            ud = md['user-script']

        self.metadata = util.mergemanydict([md, self.metadata])
        self.userdata_raw = ud
        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg

    def get_instance_id(self):
        return self.metadata['instance-id']

    def query(self, noun, strip=False, default=None, b64=None):
        if b64 is None:
            if noun in self.smartos_no_base64:
                b64 = False
            elif self.b64_all or noun in self.b64_keys:
                b64 = True

        return query_data(noun=noun, strip=strip, seed_device=self.seed,
                          seed_timeout=self.seed_timeout, default=default,
                          b64=b64)


def get_serial(seed_device, seed_timeout):
    """This is replaced in unit testing, allowing us to replace
        serial.Serial with a mocked class.

        The timeout value of 60 seconds should never be hit. The value
        is taken from SmartOS own provisioning tools. Since we are reading
        each line individually up until the single ".", the transfer is
        usually very fast (i.e. microseconds) to get the response.
    """
    if not seed_device:
        raise AttributeError("seed_device value is not set")

    ser = serial.Serial(seed_device, timeout=seed_timeout)
    if not ser.isOpen():
        raise SystemError("Unable to open %s" % seed_device)

    return ser


def query_data(noun, seed_device, seed_timeout, strip=False, default=None,
               b64=None):
    """Makes a request to via the serial console via "GET <NOUN>"

        In the response, the first line is the status, while subsequent lines
        are is the value. A blank line with a "." is used to indicate end of
        response.

        If the response is expected to be base64 encoded, then set b64encoded
        to true. Unfortantely, there is no way to know if something is 100%
        encoded, so this method relies on being told if the data is base64 or
        not.
    """

    if not noun:
        return False

    ser = get_serial(seed_device, seed_timeout)
    ser.write("GET %s\n" % noun.rstrip())
    status = str(ser.readline()).rstrip()
    response = []
    eom_found = False

    if 'SUCCESS' not in status:
        ser.close()
        return default

    while not eom_found:
        m = ser.readline()
        if m.rstrip() == ".":
            eom_found = True
        else:
            response.append(m)

    ser.close()

    if b64 is None:
        b64 = query_data('b64-%s' % noun, seed_device=seed_device,
                            seed_timeout=seed_timeout, b64=False,
                            default=False, strip=True)
        b64 = util.is_true(b64)

    resp = None
    if b64 or strip:
        resp = "".join(response).rstrip()
    else:
        resp = "".join(response)

    if b64:
        try:
            return base64.b64decode(resp)
        except TypeError:
            LOG.warn("Failed base64 decoding key '%s'", noun)
            return resp

    return resp


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

    return (sys_uuid.lower().strip(), sys_type.strip())


# Used to match classes to dependencies
datasources = [
    (DataSourceSmartOS, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
