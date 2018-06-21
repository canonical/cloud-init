# Copyright (C) 2013 Canonical Ltd.
# Copyright (c) 2018, Joyent, Inc.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

#    Datasource for provisioning on SmartOS. This works on Joyent
#        and public/private Clouds using SmartOS.
#
#    SmartOS hosts use a serial console (/dev/ttyS1) on KVM Linux Guests
#        The meta-data is transmitted via key/value pairs made by
#        requests on the console. For example, to get the hostname, you
#        would send "GET sdc:hostname" on /dev/ttyS1.
#        For Linux Guests running in LX-Brand Zones on SmartOS hosts
#        a socket (/native/.zonecontrol/metadata.sock) is used instead
#        of a serial console.
#
#   Certain behavior is defined by the DataDictionary
#       https://eng.joyent.com/mdata/datadict.html
#       Comments with "@datadictionary" are snippets of the definition

import base64
import binascii
import errno
import fcntl
import json
import os
import random
import re
import socket

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
    'hostname': ('sdc:hostname', True),
    'dns_domain': ('sdc:dns_domain', True),
}

SMARTOS_ATTRIB_JSON = {
    # Cloud-init Key : (SmartOS Key known JSON)
    'network-data': 'sdc:nics',
    'dns_servers': 'sdc:resolvers',
    'routes': 'sdc:routes',
}

SMARTOS_ENV_LX_BRAND = "lx-brand"
SMARTOS_ENV_KVM = "kvm"

DS_NAME = 'SmartOS'
DS_CFG_PATH = ['datasource', DS_NAME]
NO_BASE64_DECODE = [
    'iptables_disable',
    'motd_sys_info',
    'root_authorized_keys',
    'sdc:datacenter_name',
    'sdc:uuid'
    'user-data',
    'user-script',
]

METADATA_SOCKFILE = '/native/.zonecontrol/metadata.sock'
SERIAL_DEVICE = '/dev/ttyS1'
SERIAL_TIMEOUT = 60

# BUILT-IN DATASOURCE CONFIGURATION
#  The following is the built-in configuration. If the values
#  are not set via the system configuration, then these default
#  will be used:
#    serial_device: which serial device to use for the meta-data
#    serial_timeout: how long to wait on the device
#    no_base64_decode: values which are not base64 encoded and
#            are fetched directly from SmartOS, not meta-data values
#    base64_keys: meta-data keys that are delivered in base64
#    base64_all: with the exclusion of no_base64_decode values,
#            treat all meta-data as base64 encoded
#    disk_setup: describes how to partition the ephemeral drive
#    fs_setup: describes how to format the ephemeral drive
#
BUILTIN_DS_CONFIG = {
    'serial_device': SERIAL_DEVICE,
    'serial_timeout': SERIAL_TIMEOUT,
    'metadata_sockfile': METADATA_SOCKFILE,
    'no_base64_decode': NO_BASE64_DECODE,
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
                  'filesystem': 'ext4',
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

    dsname = "Joyent"

    smartos_type = sources.UNSET
    md_client = sources.UNSET

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.ds_cfg = util.mergemanydict([
            self.ds_cfg,
            util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}),
            BUILTIN_DS_CONFIG])

        self.metadata = {}
        self.network_data = None
        self._network_config = None

        self.script_base_d = os.path.join(self.paths.get_cpath("scripts"))

        self._init()

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [client=%s]" % (root, self.md_client)

    def _init(self):
        if self.smartos_type == sources.UNSET:
            self.smartos_type = get_smartos_environ()
            if self.smartos_type is None:
                self.md_client = None

        if self.md_client == sources.UNSET:
            self.md_client = jmc_client_factory(
                smartos_type=self.smartos_type,
                metadata_sockfile=self.ds_cfg['metadata_sockfile'],
                serial_device=self.ds_cfg['serial_device'],
                serial_timeout=self.ds_cfg['serial_timeout'])

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

    def _get_data(self):
        self._init()

        md = {}
        ud = ""

        if not self.smartos_type:
            LOG.debug("Not running on smartos")
            return False

        if not self.md_client.exists():
            LOG.debug("No metadata device '%r' found for SmartOS datasource",
                      self.md_client)
            return False

        # Open once for many requests, rather than once for each request
        self.md_client.open_transport()

        for ci_noun, attribute in SMARTOS_ATTRIB_MAP.items():
            smartos_noun, strip = attribute
            md[ci_noun] = self.md_client.get(smartos_noun, strip=strip)

        for ci_noun, smartos_noun in SMARTOS_ATTRIB_JSON.items():
            md[ci_noun] = self.md_client.get_json(smartos_noun)

        self.md_client.close_transport()

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

        # The hostname may or may not be qualified with the local domain name.
        # This follows section 3.14 of RFC 2132.
        if not md['local-hostname']:
            if md['hostname']:
                md['local-hostname'] = md['hostname']
            else:
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
        self.network_data = md['network-data']
        self.routes_data = md['routes']

        self._set_provisioned()
        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        if self.smartos_type == SMARTOS_ENV_KVM:
            return BUILTIN_CLOUD_CONFIG
        return {}

    def get_instance_id(self):
        return self.metadata['instance-id']

    @property
    def network_config(self):
        if self._network_config is None:
            if self.network_data is not None:
                self._network_config = (
                    convert_smartos_network_data(
                        network_data=self.network_data,
                        dns_servers=self.metadata['dns_servers'],
                        dns_domain=self.metadata['dns_domain'],
                        routes=self.routes_data))
        return self._network_config


class JoyentMetadataFetchException(Exception):
    pass


class JoyentMetadataTimeoutException(JoyentMetadataFetchException):
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

    def __init__(self, smartos_type=None, fp=None):
        if smartos_type is None:
            smartos_type = get_smartos_environ()
        self.smartos_type = smartos_type
        self.fp = fp

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

    def _readline(self):
        """
           Reads a line a byte at a time until \n is encountered.  Returns an
           ascii string with the trailing newline removed.

           If a timeout (per-byte) is set and it expires, a
           JoyentMetadataFetchException will be thrown.
        """
        response = []

        def as_ascii():
            return b''.join(response).decode('ascii')

        msg = "Partial response: '%s'"
        while True:
            try:
                byte = self.fp.read(1)
                if len(byte) == 0:
                    raise JoyentMetadataTimeoutException(msg % as_ascii())
                if byte == b'\n':
                    return as_ascii()
                response.append(byte)
            except OSError as exc:
                if exc.errno == errno.EAGAIN:
                    raise JoyentMetadataTimeoutException(msg % as_ascii())
                raise

    def _write(self, msg):
        self.fp.write(msg.encode('ascii'))
        self.fp.flush()

    def _negotiate(self):
        LOG.debug('Negotiating protocol V2')
        self._write('NEGOTIATE V2\n')
        response = self._readline()
        LOG.debug('read "%s"', response)
        if response != 'V2_OK':
            raise JoyentMetadataFetchException(
                'Invalid response "%s" to "NEGOTIATE V2"' % response)
        LOG.debug('Negotiation complete')

    def request(self, rtype, param=None):
        request_id = '{0:08x}'.format(random.randint(0, 0xffffffff))
        message_body = ' '.join((request_id, rtype,))
        if param:
            message_body += ' ' + base64.b64encode(param.encode()).decode()
        msg = 'V2 {0} {1} {2}\n'.format(
            len(message_body), self._checksum(message_body), message_body)
        LOG.debug('Writing "%s" to metadata transport.', msg)

        need_close = False
        if not self.fp:
            self.open_transport()
            need_close = True

        self._write(msg)
        response = self._readline()
        if need_close:
            self.close_transport()

        LOG.debug('Read "%s" from metadata transport.', response)

        if 'SUCCESS' not in response:
            return None

        value = self._get_value_from_frame(request_id, response)
        return value

    def get(self, key, default=None, strip=False):
        result = self.request(rtype='GET', param=key)
        if result is None:
            return default
        if result and strip:
            result = result.strip()
        return result

    def get_json(self, key, default=None):
        result = self.get(key, default=default)
        if result is None:
            return default
        return json.loads(result)

    def list(self):
        result = self.request(rtype='KEYS')
        if not result:
            return []
        return result.split('\n')

    def put(self, key, val):
        param = b' '.join([base64.b64encode(i.encode())
                           for i in (key, val)]).decode()
        return self.request(rtype='PUT', param=param)

    def delete(self, key):
        return self.request(rtype='DELETE', param=key)

    def close_transport(self):
        if self.fp:
            self.fp.close()
            self.fp = None

    def __enter__(self):
        if self.fp:
            return self
        self.open_transport()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close_transport()
        return

    def open_transport(self):
        raise NotImplementedError


class JoyentMetadataSocketClient(JoyentMetadataClient):
    def __init__(self, socketpath, smartos_type=SMARTOS_ENV_LX_BRAND):
        super(JoyentMetadataSocketClient, self).__init__(smartos_type)
        self.socketpath = socketpath

    def open_transport(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socketpath)
        self.fp = sock.makefile('rwb')
        self._negotiate()

    def exists(self):
        return os.path.exists(self.socketpath)

    def __repr__(self):
        return "%s(socketpath=%s)" % (self.__class__.__name__, self.socketpath)


class JoyentMetadataSerialClient(JoyentMetadataClient):
    def __init__(self, device, timeout=10, smartos_type=SMARTOS_ENV_KVM,
                 fp=None):
        super(JoyentMetadataSerialClient, self).__init__(smartos_type, fp)
        self.device = device
        self.timeout = timeout

    def exists(self):
        return os.path.exists(self.device)

    def open_transport(self):
        if self.fp is None:
            ser = serial.Serial(self.device, timeout=self.timeout)
            if not ser.isOpen():
                raise SystemError("Unable to open %s" % self.device)
            self.fp = ser
            fcntl.lockf(ser, fcntl.LOCK_EX)
        self._flush()
        self._negotiate()

    def _flush(self):
        LOG.debug('Flushing input')
        # Read any pending data
        timeout = self.fp.timeout
        self.fp.timeout = 0.1
        while True:
            try:
                self._readline()
            except JoyentMetadataTimeoutException:
                break
        LOG.debug('Input empty')

        # Send a newline and expect "invalid command".  Keep trying until
        # successful.  Retry rather frequently so that the "Is the host
        # metadata service running" appears on the console soon after someone
        # attaches in an effort to debug.
        if timeout > 5:
            self.fp.timeout = 5
        else:
            self.fp.timeout = timeout
        while True:
            LOG.debug('Writing newline, expecting "invalid command"')
            self._write('\n')
            try:
                response = self._readline()
                if response == 'invalid command':
                    break
                if response == 'FAILURE':
                    LOG.debug('Got "FAILURE".  Retrying.')
                    continue
                LOG.warning('Unexpected response "%s" during flush', response)
            except JoyentMetadataTimeoutException:
                LOG.warning('Timeout while initializing metadata client. ' +
                            'Is the host metadata service running?')
        LOG.debug('Got "invalid command".  Flush complete.')
        self.fp.timeout = timeout

    def __repr__(self):
        return "%s(device=%s, timeout=%s)" % (
            self.__class__.__name__, self.device, self.timeout)


class JoyentMetadataLegacySerialClient(JoyentMetadataSerialClient):
    """V1 of the protocol was not safe for all values.
    Thus, we allowed the user to pass values in as base64 encoded.
    Users may still reasonably expect to be able to send base64 data
    and have it transparently decoded.  So even though the V2 format is
    now used, and is safe (using base64 itself), we keep legacy support.

    The way for a user to do this was:
      a.) specify 'base64_keys' key whose value is a comma delimited
          list of keys that were base64 encoded.
      b.) base64_all: string interpreted as a boolean that indicates
          if all keys are base64 encoded.
      c.) set a key named b64-<keyname> with a boolean indicating that
          <keyname> is base64 encoded."""

    def __init__(self, device, timeout=10, smartos_type=None):
        s = super(JoyentMetadataLegacySerialClient, self)
        s.__init__(device, timeout, smartos_type)
        self.base64_keys = None
        self.base64_all = None

    def _init_base64_keys(self, reset=False):
        if reset:
            self.base64_keys = None
            self.base64_all = None

        keys = None
        if self.base64_all is None:
            keys = self.list()
            if 'base64_all' in keys:
                self.base64_all = util.is_true(self._get("base64_all"))
            else:
                self.base64_all = False

        if self.base64_all:
            # short circuit if base64_all is true
            return

        if self.base64_keys is None:
            if keys is None:
                keys = self.list()
            b64_keys = set()
            if 'base64_keys' in keys:
                b64_keys = set(self._get("base64_keys").split(","))

            # now add any b64-<keyname> that has a true value
            for key in [k[3:] for k in keys if k.startswith("b64-")]:
                if util.is_true(self._get(key)):
                    b64_keys.add(key)
                else:
                    if key in b64_keys:
                        b64_keys.remove(key)

            self.base64_keys = b64_keys

    def _get(self, key, default=None, strip=False):
        return (super(JoyentMetadataLegacySerialClient, self).
                get(key, default=default, strip=strip))

    def is_b64_encoded(self, key, reset=False):
        if key in NO_BASE64_DECODE:
            return False

        self._init_base64_keys(reset=reset)
        if self.base64_all:
            return True

        return key in self.base64_keys

    def get(self, key, default=None, strip=False):
        mdefault = object()
        val = self._get(key, strip=False, default=mdefault)
        if val is mdefault:
            return default

        if self.is_b64_encoded(key):
            try:
                val = base64.b64decode(val.encode()).decode()
            # Bogus input produces different errors in Python 2 and 3
            except (TypeError, binascii.Error):
                LOG.warning("Failed base64 decoding key '%s': %s", key, val)

        if strip:
            val = val.strip()

        return val


def jmc_client_factory(
        smartos_type=None, metadata_sockfile=METADATA_SOCKFILE,
        serial_device=SERIAL_DEVICE, serial_timeout=SERIAL_TIMEOUT,
        uname_version=None):

    if smartos_type is None:
        smartos_type = get_smartos_environ(uname_version)

    if smartos_type is None:
        return None
    elif smartos_type == SMARTOS_ENV_KVM:
        return JoyentMetadataLegacySerialClient(
            device=serial_device, timeout=serial_timeout,
            smartos_type=smartos_type)
    elif smartos_type == SMARTOS_ENV_LX_BRAND:
        return JoyentMetadataSocketClient(socketpath=metadata_sockfile,
                                          smartos_type=smartos_type)

    raise ValueError("Unknown value for smartos_type: %s" % smartos_type)


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
            util.logexc(LOG, "failed establishing content link: %s", e)


def get_smartos_environ(uname_version=None, product_name=None):
    uname = os.uname()

    # SDC LX-Brand Zones lack dmidecode (no /dev/mem) but
    # report 'BrandZ virtual linux' as the kernel version
    if uname_version is None:
        uname_version = uname[3]
    if uname_version == 'BrandZ virtual linux':
        return SMARTOS_ENV_LX_BRAND

    if product_name is None:
        system_type = util.read_dmi_data("system-product-name")
    else:
        system_type = product_name

    if system_type and system_type.startswith('SmartDC'):
        return SMARTOS_ENV_KVM

    return None


# Convert SMARTOS 'sdc:nics' data to network_config yaml
def convert_smartos_network_data(network_data=None,
                                 dns_servers=None, dns_domain=None,
                                 routes=None):
    """Return a dictionary of network_config by parsing provided
       SMARTOS sdc:nics configuration data

    sdc:nics data is a dictionary of properties of a nic and the ip
    configuration desired.  Additional nic dictionaries are appended
    to the list.

    Converting the format is straightforward though it does include
    duplicate information as well as data which appears to be relevant
    to the hostOS rather than the guest.

    For each entry in the nics list returned from query sdc:nics, we
    create a type: physical entry, and extract the interface properties:
    'mac' -> 'mac_address', 'mtu', 'interface' -> 'name'.  The remaining
    keys are related to ip configuration.  For each ip in the 'ips' list
    we create a subnet entry under 'subnets' pairing the ip to a one in
    the 'gateways' list.

    Each route in sdc:routes is mapped to a route on each interface.
    The sdc:routes properties 'dst' and 'gateway' map to 'network' and
    'gateway'.  The 'linklocal' sdc:routes property is ignored.
    """

    valid_keys = {
        'physical': [
            'mac_address',
            'mtu',
            'name',
            'params',
            'subnets',
            'type',
        ],
        'subnet': [
            'address',
            'broadcast',
            'dns_nameservers',
            'dns_search',
            'metric',
            'pointopoint',
            'routes',
            'scope',
            'type',
        ],
        'route': [
            'network',
            'gateway',
        ],
    }

    if dns_servers:
        if not isinstance(dns_servers, (list, tuple)):
            dns_servers = [dns_servers]
    else:
        dns_servers = []

    if dns_domain:
        if not isinstance(dns_domain, (list, tuple)):
            dns_domain = [dns_domain]
    else:
        dns_domain = []

    if not routes:
        routes = []

    def is_valid_ipv4(addr):
        return '.' in addr

    def is_valid_ipv6(addr):
        return ':' in addr

    pgws = {
        'ipv4': {'match': is_valid_ipv4, 'gw': None},
        'ipv6': {'match': is_valid_ipv6, 'gw': None},
    }

    config = []
    for nic in network_data:
        cfg = dict((k, v) for k, v in nic.items()
                   if k in valid_keys['physical'])
        cfg.update({
            'type': 'physical',
            'name': nic['interface']})
        if 'mac' in nic:
            cfg.update({'mac_address': nic['mac']})

        subnets = []
        for ip in nic.get('ips', []):
            if ip == "dhcp":
                subnet = {'type': 'dhcp4'}
            else:
                routeents = []
                subnet = dict((k, v) for k, v in nic.items()
                              if k in valid_keys['subnet'])
                subnet.update({
                    'type': 'static',
                    'address': ip,
                })

                proto = 'ipv4' if is_valid_ipv4(ip) else 'ipv6'
                # Only use gateways for 'primary' nics
                if 'primary' in nic and nic.get('primary', False):
                    # the ips and gateways list may be N to M, here
                    # we map the ip index into the gateways list,
                    # and handle the case that we could have more ips
                    # than gateways.  we only consume the first gateway
                    if not pgws[proto]['gw']:
                        gateways = [gw for gw in nic.get('gateways', [])
                                    if pgws[proto]['match'](gw)]
                        if len(gateways):
                            pgws[proto]['gw'] = gateways[0]
                            subnet.update({'gateway': pgws[proto]['gw']})

                for route in routes:
                    rcfg = dict((k, v) for k, v in route.items()
                                if k in valid_keys['route'])
                    # Linux uses the value of 'gateway' to determine
                    # automatically if the route is a forward/next-hop
                    # (non-local IP for gateway) or an interface/resolver
                    # (local IP for gateway).  So we can ignore the
                    # 'interface' attribute of sdc:routes, because SDC
                    # guarantees that the gateway is a local IP for
                    # "interface=true".
                    #
                    # Eventually we should be smart and compare "gateway"
                    # to see if it's in the prefix.  We can then smartly
                    # add or not-add this route.  But for now,
                    # when in doubt, use brute force! Routes for everyone!
                    rcfg.update({'network': route['dst']})
                    routeents.append(rcfg)
                    subnet.update({'routes': routeents})

            subnets.append(subnet)
        cfg.update({'subnets': subnets})
        config.append(cfg)

    if dns_servers:
        config.append(
            {'type': 'nameserver', 'address': dns_servers,
             'search': dns_domain})

    return {'version': 1, 'config': config}


# Used to match classes to dependencies
datasources = [
    (DataSourceSmartOS, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import sys
    jmc = jmc_client_factory()
    if jmc is None:
        print("Do not appear to be on smartos.")
        sys.exit(1)
    if len(sys.argv) == 1:
        keys = (list(SMARTOS_ATTRIB_JSON.keys()) +
                list(SMARTOS_ATTRIB_MAP.keys()) + ['network_config'])
    else:
        keys = sys.argv[1:]

    def load_key(client, key, data):
        if key in data:
            return data[key]

        if key in SMARTOS_ATTRIB_JSON:
            keyname = SMARTOS_ATTRIB_JSON[key]
            data[key] = client.get_json(keyname)
        elif key == "network_config":
            for depkey in ('network-data', 'dns_servers', 'dns_domain',
                           'routes'):
                load_key(client, depkey, data)
            data[key] = convert_smartos_network_data(
                network_data=data['network-data'],
                dns_servers=data['dns_servers'],
                dns_domain=data['dns_domain'],
                routes=data['routes'])
        else:
            if key in SMARTOS_ATTRIB_MAP:
                keyname, strip = SMARTOS_ATTRIB_MAP[key]
            else:
                keyname, strip = (key, False)
            data[key] = client.get(keyname, strip=strip)

        return data[key]

    data = {}
    for key in keys:
        load_key(client=jmc, key=key, data=data)

    print(json.dumps(data, indent=1, sort_keys=True,
                     separators=(',', ': ')))

# vi: ts=4 expandtab
