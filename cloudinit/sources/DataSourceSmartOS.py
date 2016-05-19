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
#    SmartOS hosts use a serial console (/dev/ttyS1) on KVM Linux Guests
#        The meta-data is transmitted via key/value pairs made by
#        requests on the console. For example, to get the hostname, you
#        would send "GET hostname" on /dev/ttyS1.
#        For Linux Guests running in LX-Brand Zones on SmartOS hosts
#        a socket (/native/.zonecontrol/metadata.sock) is used instead
#        of a serial console.
#
#   Certain behavior is defined by the DataDictionary
#       http://us-east.manta.joyent.com/jmc/public/mdata/datadict.html
#       Comments with "@datadictionary" are snippets of the definition

import binascii
import contextlib
import os
import random
import re
import socket
import stat

from cloudinit import log as logging
from cloudinit import serial
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

SMARTOS_ATTRIB_MAP = {
    # Cloud-init Key : (SmartOS Key, Strip line endings)
    'instance-id': ('sdc:uuid', True),
    'local-hostname': ('hostname', True),
    'public-keys': ('root_authorized_keys', True),
    'user-script': ('user-script', False),
    'legacy-user-data': ('user-data', False),
    'user-data': ('cloud-init:user-data', False),
    'iptables_disable': ('iptables_disable', True),
    'motd_sys_info': ('motd_sys_info', True),
    'availability_zone': ('sdc:datacenter_name', True),
    'vendor-data': ('sdc:vendor-data', False),
    'operator-script': ('sdc:operator-script', False),
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
    'metadata_sockfile': '/native/.zonecontrol/metadata.sock',
    'seed_timeout': 60,
    'no_base64_decode': ['root_authorized_keys',
                         'motd_sys_info',
                         'iptables_disable',
                         'user-data',
                         'user-script',
                         'sdc:datacenter_name',
                         'sdc:uuid'],
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

# builtin vendor-data is a boothook that writes a script into
# /var/lib/cloud/scripts/per-boot.  *That* script then handles
# executing the 'operator-script' and 'user-script' files
# that cloud-init writes into /var/lib/cloud/instance/data/
# if they exist.
#
# This is all very indirect, but its done like this so that at
# some point in the future, perhaps cloud-init wouldn't do it at
# all, but rather the vendor actually provide vendor-data that accomplished
# their desires. (That is the point of vendor-data).
#
# cloud-init does cheat a bit, and write the operator-script and user-script
# itself.  It could have the vendor-script do that, but it seems better
# to not require the image to contain a tool (mdata-get) to read those
# keys when we have a perfectly good one inside cloud-init.
BUILTIN_VENDOR_DATA = """\
#cloud-boothook
#!/bin/sh
fname="%(per_boot_d)s/01_smartos_vendor_data.sh"
mkdir -p "${fname%%/*}"
cat > "$fname" <<"END_SCRIPT"
#!/bin/sh
##
# This file is written as part of the default vendor data for SmartOS.
# The SmartOS datasource writes the listed file from the listed metadata key
#   sdc:operator-script -> %(operator_script)s
#   user-script -> %(user_script)s
#
# You can view content with 'mdata-get <key>'
#
for script in "%(operator_script)s" "%(user_script)s"; do
    [ -x "$script" ] || continue
    echo "executing '$script'" 1>&2
    "$script"
done
END_SCRIPT
chmod +x "$fname"
"""


# @datadictionary: this is legacy path for placing files from metadata
#   per the SmartOS location. It is not preferable, but is done for
#   legacy reasons
LEGACY_USER_D = "/var/db"


class DataSourceSmartOS(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.is_smartdc = None
        self.ds_cfg = util.mergemanydict([
            self.ds_cfg,
            util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}),
            BUILTIN_DS_CONFIG])

        self.metadata = {}

        # SDC LX-Brand Zones lack dmidecode (no /dev/mem) but
        # report 'BrandZ virtual linux' as the kernel version
        if os.uname()[3].lower() == 'brandz virtual linux':
            LOG.debug("Host is SmartOS, guest in Zone")
            self.is_smartdc = True
            self.smartos_type = 'lx-brand'
            self.cfg = {}
            self.seed = self.ds_cfg.get("metadata_sockfile")
        else:
            self.is_smartdc = True
            self.smartos_type = 'kvm'
            self.seed = self.ds_cfg.get("serial_device")
            self.cfg = BUILTIN_CLOUD_CONFIG
            self.seed_timeout = self.ds_cfg.get("serial_timeout")
        self.smartos_no_base64 = self.ds_cfg.get('no_base64_decode')
        self.b64_keys = self.ds_cfg.get('base64_keys')
        self.b64_all = self.ds_cfg.get('base64_all')
        self.script_base_d = os.path.join(self.paths.get_cpath("scripts"))

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def _get_seed_file_object(self):
        if not self.seed:
            raise AttributeError("seed device is not set")

        if self.smartos_type == 'lx-brand':
            if not stat.S_ISSOCK(os.stat(self.seed).st_mode):
                LOG.debug("Seed %s is not a socket", self.seed)
                return None
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.seed)
            return sock.makefile('rwb')
        else:
            if not stat.S_ISCHR(os.stat(self.seed).st_mode):
                LOG.debug("Seed %s is not a character device")
                return None
            ser = serial.Serial(self.seed, timeout=self.seed_timeout)
            if not ser.isOpen():
                raise SystemError("Unable to open %s" % self.seed)
            return ser
        return None

    def _set_provisioned(self):
        '''Mark the instance provisioning state as successful.

        When run in a zone, the host OS will look for /var/svc/provisioning
        to be renamed as /var/svc/provision_success.   This should be done
        after meta-data is successfully retrieved and from this point
        the host considers the provision of the zone to be a success and
        keeps the zone running.
        '''

        LOG.debug('Instance provisioning state set as successful')
        svc_path = '/var/svc'
        if os.path.exists('/'.join([svc_path, 'provisioning'])):
            os.rename('/'.join([svc_path, 'provisioning']),
                      '/'.join([svc_path, 'provision_success']))

    def get_data(self):
        md = {}
        ud = ""

        if not device_exists(self.seed):
            LOG.debug("No metadata device '%s' found for SmartOS datasource",
                      self.seed)
            return False

        uname_arch = os.uname()[4]
        if uname_arch.startswith("arm") or uname_arch == "aarch64":
            # Disabling because dmidcode in dmi_data() crashes kvm process
            LOG.debug("Disabling SmartOS datasource on arm (LP: #1243287)")
            return False

        # SDC KVM instances will provide dmi data, LX-brand does not
        if self.smartos_type == 'kvm':
            dmi_info = dmi_data()
            if dmi_info is None:
                LOG.debug("No dmidata utility found")
                return False

            system_type = dmi_info
            if 'smartdc' not in system_type.lower():
                LOG.debug("Host is not on SmartOS. system_type=%s",
                          system_type)
                return False
            LOG.debug("Host is SmartOS, guest in KVM")

        seed_obj = self._get_seed_file_object()
        if seed_obj is None:
            LOG.debug('Seed file object not found.')
            return False
        with contextlib.closing(seed_obj) as seed:
            b64_keys = self.query('base64_keys', seed, strip=True, b64=False)
            if b64_keys is not None:
                self.b64_keys = [k.strip() for k in str(b64_keys).split(',')]

            b64_all = self.query('base64_all', seed, strip=True, b64=False)
            if b64_all is not None:
                self.b64_all = util.is_true(b64_all)

            for ci_noun, attribute in SMARTOS_ATTRIB_MAP.items():
                smartos_noun, strip = attribute
                md[ci_noun] = self.query(smartos_noun, seed, strip=strip)

        # @datadictionary: This key may contain a program that is written
        # to a file in the filesystem of the guest on each boot and then
        # executed. It may be of any format that would be considered
        # executable in the guest instance.
        #
        # We write 'user-script' and 'operator-script' into the
        # instance/data directory. The default vendor-data then handles
        # executing them later.
        data_d = os.path.join(self.paths.get_cpath(), 'instances',
                              md['instance-id'], 'data')
        user_script = os.path.join(data_d, 'user-script')
        u_script_l = "%s/user-script" % LEGACY_USER_D
        write_boot_content(md.get('user-script'), content_f=user_script,
                           link=u_script_l, shebang=True, mode=0o700)

        operator_script = os.path.join(data_d, 'operator-script')
        write_boot_content(md.get('operator-script'),
                           content_f=operator_script, shebang=False,
                           mode=0o700)

        # @datadictionary:  This key has no defined format, but its value
        # is written to the file /var/db/mdata-user-data on each boot prior
        # to the phase that runs user-script. This file is not to be executed.
        # This allows a configuration file of some kind to be injected into
        # the machine to be consumed by the user-script when it runs.
        u_data = md.get('legacy-user-data')
        u_data_f = "%s/mdata-user-data" % LEGACY_USER_D
        write_boot_content(u_data, u_data_f)

        # Handle the cloud-init regular meta
        if not md['local-hostname']:
            md['local-hostname'] = md['instance-id']

        ud = None
        if md['user-data']:
            ud = md['user-data']

        if not md['vendor-data']:
            md['vendor-data'] = BUILTIN_VENDOR_DATA % {
                'user_script': user_script,
                'operator_script': operator_script,
                'per_boot_d': os.path.join(self.paths.get_cpath("scripts"),
                                           'per-boot'),
            }

        self.metadata = util.mergemanydict([md, self.metadata])
        self.userdata_raw = ud
        self.vendordata_raw = md['vendor-data']

        self._set_provisioned()
        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg

    def get_instance_id(self):
        return self.metadata['instance-id']

    def query(self, noun, seed_file, strip=False, default=None, b64=None):
        if b64 is None:
            if noun in self.smartos_no_base64:
                b64 = False
            elif self.b64_all or noun in self.b64_keys:
                b64 = True

        return self._query_data(noun, seed_file, strip=strip,
                                default=default, b64=b64)

    def _query_data(self, noun, seed_file, strip=False,
                    default=None, b64=None):
        """Makes a request via "GET <NOUN>"

           In the response, the first line is the status, while subsequent
           lines are is the value. A blank line with a "." is used to
           indicate end of response.

           If the response is expected to be base64 encoded, then set
           b64encoded to true. Unfortantely, there is no way to know if
           something is 100% encoded, so this method relies on being told
           if the data is base64 or not.
        """

        if not noun:
            return False

        response = JoyentMetadataClient(seed_file).get_metadata(noun)

        if response is None:
            return default

        if b64 is None:
            b64 = self._query_data('b64-%s' % noun, seed_file, b64=False,
                                   default=False, strip=True)
            b64 = util.is_true(b64)

        resp = None
        if b64 or strip:
            resp = "".join(response).rstrip()
        else:
            resp = "".join(response)

        if b64:
            try:
                return util.b64d(resp)
            # Bogus input produces different errors in Python 2 and 3;
            # catch both.
            except (TypeError, binascii.Error):
                LOG.warn("Failed base64 decoding key '%s'", noun)
                return resp

        return resp


def device_exists(device):
    """Symplistic method to determine if the device exists or not"""
    return os.path.exists(device)


class JoyentMetadataFetchException(Exception):
    pass


class JoyentMetadataClient(object):
    """
    A client implementing v2 of the Joyent Metadata Protocol Specification.

    The full specification can be found at
    http://eng.joyent.com/mdata/protocol.html
    """
    line_regex = re.compile(
        r'V2 (?P<length>\d+) (?P<checksum>[0-9a-f]+)'
        r' (?P<body>(?P<request_id>[0-9a-f]+) (?P<status>SUCCESS|NOTFOUND)'
        r'( (?P<payload>.+))?)')

    def __init__(self, metasource):
        self.metasource = metasource

    def _checksum(self, body):
        return '{0:08x}'.format(
            binascii.crc32(body.encode('utf-8')) & 0xffffffff)

    def _get_value_from_frame(self, expected_request_id, frame):
        frame_data = self.line_regex.match(frame).groupdict()
        if int(frame_data['length']) != len(frame_data['body']):
            raise JoyentMetadataFetchException(
                'Incorrect frame length given ({0} != {1}).'.format(
                    frame_data['length'], len(frame_data['body'])))
        expected_checksum = self._checksum(frame_data['body'])
        if frame_data['checksum'] != expected_checksum:
            raise JoyentMetadataFetchException(
                'Invalid checksum (expected: {0}; got {1}).'.format(
                    expected_checksum, frame_data['checksum']))
        if frame_data['request_id'] != expected_request_id:
            raise JoyentMetadataFetchException(
                'Request ID mismatch (expected: {0}; got {1}).'.format(
                    expected_request_id, frame_data['request_id']))
        if not frame_data.get('payload', None):
            LOG.debug('No value found.')
            return None
        value = util.b64d(frame_data['payload'])
        LOG.debug('Value "%s" found.', value)
        return value

    def get_metadata(self, metadata_key):
        LOG.debug('Fetching metadata key "%s"...', metadata_key)
        request_id = '{0:08x}'.format(random.randint(0, 0xffffffff))
        message_body = '{0} GET {1}'.format(request_id,
                                            util.b64e(metadata_key))
        msg = 'V2 {0} {1} {2}\n'.format(
            len(message_body), self._checksum(message_body), message_body)
        LOG.debug('Writing "%s" to metadata transport.', msg)
        self.metasource.write(msg.encode('ascii'))
        self.metasource.flush()

        response = bytearray()
        response.extend(self.metasource.read(1))
        while response[-1:] != b'\n':
            response.extend(self.metasource.read(1))
        response = response.rstrip().decode('ascii')
        LOG.debug('Read "%s" from metadata transport.', response)

        if 'SUCCESS' not in response:
            return None

        return self._get_value_from_frame(request_id, response)


def dmi_data():
    sys_type = util.read_dmi_data("system-product-name")

    if not sys_type:
        return None

    return sys_type


def write_boot_content(content, content_f, link=None, shebang=False,
                       mode=0o400):
    """
    Write the content to content_f. Under the following rules:
        1. If no content, remove the file
        2. Write the content
        3. If executable and no file magic, add it
        4. If there is a link, create it

    @param content: what to write
    @param content_f: the file name
    @param backup_d: the directory to save the backup at
    @param link: if defined, location to create a symlink to
    @param shebang: if no file magic, set shebang
    @param mode: file mode

    Becuase of the way that Cloud-init executes scripts (no shell),
    a script will fail to execute if does not have a magic bit (shebang) set
    for the file. If shebang=True, then the script will be checked for a magic
    bit and to the SmartOS default of assuming that bash.
    """

    if not content and os.path.exists(content_f):
        os.unlink(content_f)
    if link and os.path.islink(link):
        os.unlink(link)
    if not content:
        return

    util.write_file(content_f, content, mode=mode)

    if shebang and not content.startswith("#!"):
        try:
            cmd = ["file", "--brief", "--mime-type", content_f]
            (f_type, _err) = util.subp(cmd)
            LOG.debug("script %s mime type is %s", content_f, f_type)
            if f_type.strip() == "text/plain":
                new_content = "\n".join(["#!/bin/bash", content])
                util.write_file(content_f, new_content, mode=mode)
                LOG.debug("added shebang to file %s", content_f)

        except Exception as e:
            util.logexc(LOG, ("Failed to identify script type for %s" %
                              content_f, e))

    if link:
        try:
            if os.path.islink(link):
                os.unlink(link)
            if content and os.path.exists(content_f):
                util.ensure_dir(os.path.dirname(link))
                os.symlink(content_f, link)
        except IOError as e:
            util.logexc(LOG, "failed establishing content link", e)


# Used to match classes to dependencies
datasources = [
    (DataSourceSmartOS, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
