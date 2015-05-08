# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import base64
import contextlib
import crypt
import fnmatch
import os
import os.path
import re
import socket
import struct
import tempfile
import time
from contextlib import contextmanager
from xml.dom import minidom
from xml.etree import ElementTree

from cloudinit import log as logging
from cloudinit.settings import PER_ALWAYS
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DS_NAME = 'Azure'
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}
BOUNCE_COMMAND = ['sh', '-xc',
    "i=$interface; x=0; ifdown $i || x=$?; ifup $i || x=$?; exit $x"]
DATA_DIR_CLEAN_LIST = ['SharedConfig.xml']

BUILTIN_DS_CONFIG = {
    'data_dir': "/var/lib/waagent",
    'set_hostname': True,
    'hostname_bounce': {
        'interface': 'eth0',
        'policy': True,
        'command': BOUNCE_COMMAND,
        'hostname_command': 'hostname',
        },
    'disk_aliases': {'ephemeral0': '/dev/sdb'},
}

BUILTIN_CLOUD_CONFIG = {
    'disk_setup': {
        'ephemeral0': {'table_type': 'gpt',
                       'layout': [100],
                       'overwrite': True},
        },
    'fs_setup': [{'filesystem': 'ext4',
                  'device': 'ephemeral0.1',
                  'replace_fs': 'ntfs'}],
}

DS_CFG_PATH = ['datasource', DS_NAME]
DEF_EPHEMERAL_LABEL = 'Temporary Storage'



@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


class AzureEndpointHttpClient(object):

    headers = {
        'x-ms-agent-name': 'WALinuxAgent',
        'x-ms-version': '2012-11-30',
    }

    def __init__(self, certificate):
        self.extra_secure_headers = {
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": certificate,
        }

    def get(self, url, secure=False):
        headers = self.headers
        if secure:
            headers = self.headers.copy()
            headers.update(self.extra_secure_headers)
        return util.read_file_or_url(url, headers=headers)

    def post(self, url, data=None, extra_headers=None):
        headers = self.headers
        if extra_headers is not None:
            headers = self.headers.copy()
            headers.update(extra_headers)
        return util.read_file_or_url(url, data=data, headers=headers)


class GoalState(object):

    def __init__(self, xml, http_client):
        self.http_client = http_client
        self.root = ElementTree.fromstring(xml)
        self._certificates_xml = None

    def _text_from_xpath(self, xpath):
        element = self.root.find(xpath)
        if element is not None:
            return element.text
        return None

    @property
    def container_id(self):
        return self._text_from_xpath('./Container/ContainerId')

    @property
    def incarnation(self):
        return self._text_from_xpath('./Incarnation')

    @property
    def instance_id(self):
        return self._text_from_xpath(
            './Container/RoleInstanceList/RoleInstance/InstanceId')

    @property
    def shared_config_xml(self):
        url = self._text_from_xpath('./Container/RoleInstanceList/RoleInstance'
                                    '/Configuration/SharedConfig')
        return self.http_client.get(url).contents

    @property
    def certificates_xml(self):
        if self._certificates_xml is None:
            url = self._text_from_xpath(
                './Container/RoleInstanceList/RoleInstance'
                '/Configuration/Certificates')
            if url is not None:
                self._certificates_xml = self.http_client.get(
                    url, secure=True).contents
        return self._certificates_xml


class OpenSSLManager(object):

    certificate_names = {
        'private_key': 'TransportPrivate.pem',
        'certificate': 'TransportCert.pem',
    }

    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.certificate = None
        self.generate_certificate()

    def generate_certificate(self):
        LOG.debug('Generating certificate for communication with fabric...')
        if self.certificate is not None:
            LOG.debug('Certificate already generated.')
            return
        with cd(self.tmpdir.name):
            util.subp([
                'openssl', 'req', '-x509', '-nodes', '-subj',
                '/CN=LinuxTransport', '-days', '32768', '-newkey', 'rsa:2048',
                '-keyout', self.certificate_names['private_key'],
                '-out', self.certificate_names['certificate'],
            ])
            certificate = ''
            for line in open(self.certificate_names['certificate']):
                if "CERTIFICATE" not in line:
                    certificate += line.rstrip()
            self.certificate = certificate
        LOG.debug('New certificate generated.')

    def parse_certificates(self, certificates_xml):
        tag = ElementTree.fromstring(certificates_xml).find(
            './/Data')
        certificates_content = tag.text
        lines = [
            b'MIME-Version: 1.0',
            b'Content-Disposition: attachment; filename="Certificates.p7m"',
            b'Content-Type: application/x-pkcs7-mime; name="Certificates.p7m"',
            b'Content-Transfer-Encoding: base64',
            b'',
            certificates_content.encode('utf-8'),
        ]
        with cd(self.tmpdir.name):
            with open('Certificates.p7m', 'wb') as f:
                f.write(b'\n'.join(lines))
            out, _ = util.subp(
                'openssl cms -decrypt -in Certificates.p7m -inkey'
                ' {private_key} -recip {certificate} | openssl pkcs12 -nodes'
                ' -password pass:'.format(**self.certificate_names),
                shell=True)
        private_keys, certificates = [], []
        current = []
        for line in out.splitlines():
            current.append(line)
            if re.match(r'[-]+END .*?KEY[-]+$', line):
                private_keys.append('\n'.join(current))
                current = []
            elif re.match(r'[-]+END .*?CERTIFICATE[-]+$', line):
                certificates.append('\n'.join(current))
                current = []
        keys = []
        for certificate in certificates:
            with cd(self.tmpdir.name):
                public_key, _ = util.subp(
                    'openssl x509 -noout -pubkey |'
                    'ssh-keygen -i -m PKCS8 -f /dev/stdin',
                    data=certificate,
                    shell=True)
            keys.append(public_key)
        return keys


class WALinuxAgentShim(object):

    REPORT_READY_XML_TEMPLATE = '\n'.join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Health xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
        '  <GoalStateIncarnation>{incarnation}</GoalStateIncarnation>',
        '  <Container>',
        '    <ContainerId>{container_id}</ContainerId>',
        '    <RoleInstanceList>',
        '      <Role>',
        '        <InstanceId>{instance_id}</InstanceId>',
        '        <Health>',
        '          <State>Ready</State>',
        '        </Health>',
        '      </Role>',
        '    </RoleInstanceList>',
        '  </Container>',
        '</Health>'])

    def __init__(self):
        LOG.debug('WALinuxAgentShim instantiated...')
        self.endpoint = self.find_endpoint()
        self.openssl_manager = OpenSSLManager()
        self.http_client = AzureEndpointHttpClient(
            self.openssl_manager.certificate)
        self.values = {}

    @staticmethod
    def find_endpoint():
        LOG.debug('Finding Azure endpoint...')
        content = util.load_file('/var/lib/dhcp/dhclient.eth0.leases')
        value = None
        for line in content.splitlines():
            if 'unknown-245' in line:
                value = line.strip(' ').split(' ', 2)[-1].strip(';\n"')
        if value is None:
            raise Exception('No endpoint found in DHCP config.')
        if ':' in value:
            hex_string = ''
            for hex_pair in value.split(':'):
                if len(hex_pair) == 1:
                    hex_pair = '0' + hex_pair
                hex_string += hex_pair
            value = struct.pack('>L', int(hex_string.replace(':', ''), 16))
        else:
            value = value.encode('utf-8')
        endpoint_ip_address = socket.inet_ntoa(value)
        LOG.debug('Azure endpoint found at %s', endpoint_ip_address)
        return endpoint_ip_address

    def register_with_azure_and_fetch_data(self):
        LOG.info('Registering with Azure...')
        for i in range(10):
            try:
                response = self.http_client.get(
                    'http://{}/machine/?comp=goalstate'.format(self.endpoint))
            except Exception:
                time.sleep(i + 1)
            else:
                break
        LOG.debug('Successfully fetched GoalState XML.')
        goal_state = GoalState(response.contents, self.http_client)
        public_keys = []
        if goal_state.certificates_xml is not None:
            LOG.debug('Certificate XML found; parsing out public keys.')
            public_keys = self.openssl_manager.parse_certificates(
                goal_state.certificates_xml)
        data = {
            'instance-id': iid_from_shared_config_content(
                goal_state.shared_config_xml),
            'public-keys': public_keys,
        }
        self._report_ready(goal_state)
        return data

    def _report_ready(self, goal_state):
        LOG.debug('Reporting ready to Azure fabric.')
        document = self.REPORT_READY_XML_TEMPLATE.format(
            incarnation=goal_state.incarnation,
            container_id=goal_state.container_id,
            instance_id=goal_state.instance_id,
        )
        self.http_client.post(
            "http://{}/machine?comp=health".format(self.endpoint),
            data=document,
            extra_headers={'Content-Type': 'text/xml; charset=utf-8'},
        )
        LOG.info('Reported ready to Azure fabric.')


def get_hostname(hostname_command='hostname'):
    return util.subp(hostname_command, capture=True)[0].strip()


def set_hostname(hostname, hostname_command='hostname'):
    util.subp([hostname_command, hostname])


@contextlib.contextmanager
def temporary_hostname(temp_hostname, cfg, hostname_command='hostname'):
    """
    Set a temporary hostname, restoring the previous hostname on exit.

    Will have the value of the previous hostname when used as a context
    manager, or None if the hostname was not changed.
    """
    policy = cfg['hostname_bounce']['policy']
    previous_hostname = get_hostname(hostname_command)
    if (not util.is_true(cfg.get('set_hostname'))
            or util.is_false(policy)
            or (previous_hostname == temp_hostname and policy != 'force')):
        yield None
        return
    set_hostname(temp_hostname, hostname_command)
    try:
        yield previous_hostname
    finally:
        set_hostname(previous_hostname, hostname_command)


class DataSourceAzureNet(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'azure')
        self.cfg = {}
        self.seed = None
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}),
            BUILTIN_DS_CONFIG])

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        # azure removes/ejects the cdrom containing the ovf-env.xml
        # file on reboot.  So, in order to successfully reboot we
        # need to look in the datadir and consider that valid
        ddir = self.ds_cfg['data_dir']

        candidates = [self.seed_dir]
        candidates.extend(list_possible_azure_ds_devs())
        if ddir:
            candidates.append(ddir)

        found = None

        for cdev in candidates:
            try:
                if cdev.startswith("/dev/"):
                    ret = util.mount_cb(cdev, load_azure_ds_dir)
                else:
                    ret = load_azure_ds_dir(cdev)

            except NonAzureDataSource:
                continue
            except BrokenAzureDataSource as exc:
                raise exc
            except util.MountFailedError:
                LOG.warn("%s was not mountable", cdev)
                continue

            (md, self.userdata_raw, cfg, files) = ret
            self.seed = cdev
            self.metadata = util.mergemanydict([md, DEFAULT_METADATA])
            self.cfg = util.mergemanydict([cfg, BUILTIN_CLOUD_CONFIG])
            found = cdev

            LOG.debug("found datasource in %s", cdev)
            break

        if not found:
            return False

        if found == ddir:
            LOG.debug("using files cached in %s", ddir)

        # azure / hyper-v provides random data here
        seed = util.load_file("/sys/firmware/acpi/tables/OEM0",
                              quiet=True, decode=False)
        if seed:
            self.metadata['random_seed'] = seed

        # now update ds_cfg to reflect contents pass in config
        user_ds_cfg = util.get_cfg_by_path(self.cfg, DS_CFG_PATH, {})
        self.ds_cfg = util.mergemanydict([user_ds_cfg, self.ds_cfg])
        mycfg = self.ds_cfg
        ddir = mycfg['data_dir']

        if found != ddir:
            cached_ovfenv = util.load_file(
                os.path.join(ddir, 'ovf-env.xml'), quiet=True, decode=False)
            if cached_ovfenv != files['ovf-env.xml']:
                # source was not walinux-agent's datadir, so we have to clean
                # up so 'wait_for_files' doesn't return early due to stale data
                cleaned = []
                for f in [os.path.join(ddir, f) for f in DATA_DIR_CLEAN_LIST]:
                    if os.path.exists(f):
                        util.del_file(f)
                        cleaned.append(f)
                if cleaned:
                    LOG.info("removed stale file(s) in '%s': %s",
                             ddir, str(cleaned))

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(ddir, files, dirmode=0o700)

        try:
            shim = WALinuxAgentShim()
            data = shim.register_with_azure_and_fetch_data()
        except Exception as exc:
            LOG.info("Error communicating with Azure fabric; assume we aren't"
                     " on Azure.", exc_info=True)
            return False

        self.metadata['instance-id'] = data['instance-id']
        self.metadata['public-keys'] = data['public-keys']

        found_ephemeral = find_ephemeral_disk()
        if found_ephemeral:
            self.ds_cfg['disk_aliases']['ephemeral0'] = found_ephemeral
            LOG.debug("using detected ephemeral0 of %s", found_ephemeral)

        cc_modules_override = support_new_ephemeral(self.sys_cfg)
        if cc_modules_override:
            self.cfg['cloud_config_modules'] = cc_modules_override

        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg


def count_files(mp):
    return len(fnmatch.filter(os.listdir(mp), '*[!cdrom]*'))


def find_ephemeral_part():
    """
    Locate the default ephmeral0.1 device. This will be the first device
    that has a LABEL of DEF_EPHEMERAL_LABEL and is a NTFS device. If Azure
    gets more ephemeral devices, this logic will only identify the first
    such device.
    """
    c_label_devs = util.find_devs_with("LABEL=%s" % DEF_EPHEMERAL_LABEL)
    c_fstype_devs = util.find_devs_with("TYPE=ntfs")
    for dev in c_label_devs:
        if dev in c_fstype_devs:
            return dev
    return None


def find_ephemeral_disk():
    """
    Get the ephemeral disk.
    """
    part_dev = find_ephemeral_part()
    if part_dev and str(part_dev[-1]).isdigit():
        return part_dev[:-1]
    elif part_dev:
        return part_dev
    return None


def support_new_ephemeral(cfg):
    """
    Windows Azure makes ephemeral devices ephemeral to boot; a ephemeral device
    may be presented as a fresh device, or not.

    Since the knowledge of when a disk is supposed to be plowed under is
    specific to Windows Azure, the logic resides here in the datasource. When a
    new ephemeral device is detected, cloud-init overrides the default
    frequency for both disk-setup and mounts for the current boot only.
    """
    device = find_ephemeral_part()
    if not device:
        LOG.debug("no default fabric formated ephemeral0.1 found")
        return None
    LOG.debug("fabric formated ephemeral0.1 device at %s", device)

    file_count = 0
    try:
        file_count = util.mount_cb(device, count_files)
    except:
        return None
    LOG.debug("fabric prepared ephmeral0.1 has %s files on it", file_count)

    if file_count >= 1:
        LOG.debug("fabric prepared ephemeral0.1 will be preserved")
        return None
    else:
        # if device was already mounted, then we need to unmount it
        # race conditions could allow for a check-then-unmount
        # to have a false positive. so just unmount and then check.
        try:
            util.subp(['umount', device])
        except util.ProcessExecutionError as e:
            if device in util.mounts():
                LOG.warn("Failed to unmount %s, will not reformat.", device)
                LOG.debug("Failed umount: %s", e)
                return None

    LOG.debug("cloud-init will format ephemeral0.1 this boot.")
    LOG.debug("setting disk_setup and mounts modules 'always' for this boot")

    cc_modules = cfg.get('cloud_config_modules')
    if not cc_modules:
        return None

    mod_list = []
    for mod in cc_modules:
        if mod in ("disk_setup", "mounts"):
            mod_list.append([mod, PER_ALWAYS])
            LOG.debug("set module '%s' to 'always' for this boot", mod)
        else:
            mod_list.append(mod)
    return mod_list


def perform_hostname_bounce(hostname, cfg, prev_hostname):
    # set the hostname to 'hostname' if it is not already set to that.
    # then, if policy is not off, bounce the interface using command
    command = cfg['command']
    interface = cfg['interface']
    policy = cfg['policy']

    msg = ("hostname=%s policy=%s interface=%s" %
           (hostname, policy, interface))
    env = os.environ.copy()
    env['interface'] = interface
    env['hostname'] = hostname
    env['old_hostname'] = prev_hostname

    if command == "builtin":
        command = BOUNCE_COMMAND

    LOG.debug("pubhname: publishing hostname [%s]", msg)
    shell = not isinstance(command, (list, tuple))
    # capture=False, see comments in bug 1202758 and bug 1206164.
    util.log_time(logfunc=LOG.debug, msg="publishing hostname",
                  get_uptime=True, func=util.subp,
                  kwargs={'args': command, 'shell': shell, 'capture': False,
                          'env': env})


def crtfile_to_pubkey(fname, data=None):
    pipeline = ('openssl x509 -noout -pubkey < "$0" |'
                'ssh-keygen -i -m PKCS8 -f /dev/stdin')
    (out, _err) = util.subp(['sh', '-c', pipeline, fname],
                            capture=True, data=data)
    return out.rstrip()


def pubkeys_from_crt_files(flist):
    pubkeys = []
    errors = []
    for fname in flist:
        try:
            pubkeys.append(crtfile_to_pubkey(fname))
        except util.ProcessExecutionError:
            errors.append(fname)

    if errors:
        LOG.warn("failed to convert the crt files to pubkey: %s", errors)

    return pubkeys


def wait_for_files(flist, maxwait=60, naplen=.5):
    need = set(flist)
    waited = 0
    while waited < maxwait:
        need -= set([f for f in need if os.path.exists(f)])
        if len(need) == 0:
            return []
        time.sleep(naplen)
        waited += naplen
    return need


def write_files(datadir, files, dirmode=None):
    if not datadir:
        return
    if not files:
        files = {}
    util.ensure_dir(datadir, dirmode)
    for (name, content) in files.items():
        util.write_file(filename=os.path.join(datadir, name),
                        content=content, mode=0o600)


def invoke_agent(cmd):
    # this is a function itself to simplify patching it for test
    if cmd:
        LOG.debug("invoking agent: %s", cmd)
        util.subp(cmd, shell=(not isinstance(cmd, list)))
    else:
        LOG.debug("not invoking agent")


def find_child(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return ret


def load_azure_ovf_pubkeys(sshnode):
    # This parses a 'SSH' node formatted like below, and returns
    # an array of dicts.
    #  [{'fp': '6BE7A7C3C8A8F4B123CCA5D0C2F1BE4CA7B63ED7',
    #    'path': 'where/to/go'}]
    #
    # <SSH><PublicKeys>
    #   <PublicKey><Fingerprint>ABC</FingerPrint><Path>/ABC</Path>
    #   ...
    # </PublicKeys></SSH>
    results = find_child(sshnode, lambda n: n.localName == "PublicKeys")
    if len(results) == 0:
        return []
    if len(results) > 1:
        raise BrokenAzureDataSource("Multiple 'PublicKeys'(%s) in SSH node" %
                                    len(results))

    pubkeys_node = results[0]
    pubkeys = find_child(pubkeys_node, lambda n: n.localName == "PublicKey")

    if len(pubkeys) == 0:
        return []

    found = []
    text_node = minidom.Document.TEXT_NODE

    for pk_node in pubkeys:
        if not pk_node.hasChildNodes():
            continue
        cur = {'fingerprint': "", 'path': ""}
        for child in pk_node.childNodes:
            if child.nodeType == text_node or not child.localName:
                continue

            name = child.localName.lower()

            if name not in cur.keys():
                continue

            if (len(child.childNodes) != 1 or
                    child.childNodes[0].nodeType != text_node):
                continue

            cur[name] = child.childNodes[0].wholeText.strip()
        found.append(cur)

    return found


def single_node_at_path(node, pathlist):
    curnode = node
    for tok in pathlist:
        results = find_child(curnode, lambda n: n.localName == tok)
        if len(results) == 0:
            raise ValueError("missing %s token in %s" % (tok, str(pathlist)))
        if len(results) > 1:
            raise ValueError("found %s nodes of type %s looking for %s" %
                             (len(results), tok, str(pathlist)))
        curnode = results[0]

    return curnode


def read_azure_ovf(contents):
    try:
        dom = minidom.parseString(contents)
    except Exception as e:
        raise BrokenAzureDataSource("invalid xml: %s" % e)

    results = find_child(dom.documentElement,
        lambda n: n.localName == "ProvisioningSection")

    if len(results) == 0:
        raise NonAzureDataSource("No ProvisioningSection")
    if len(results) > 1:
        raise BrokenAzureDataSource("found '%d' ProvisioningSection items" %
                                    len(results))
    provSection = results[0]

    lpcs_nodes = find_child(provSection,
        lambda n: n.localName == "LinuxProvisioningConfigurationSet")

    if len(results) == 0:
        raise NonAzureDataSource("No LinuxProvisioningConfigurationSet")
    if len(results) > 1:
        raise BrokenAzureDataSource("found '%d' %ss" %
                                    ("LinuxProvisioningConfigurationSet",
                                     len(results)))
    lpcs = lpcs_nodes[0]

    if not lpcs.hasChildNodes():
        raise BrokenAzureDataSource("no child nodes of configuration set")

    md_props = 'seedfrom'
    md = {'azure_data': {}}
    cfg = {}
    ud = ""
    password = None
    username = None

    for child in lpcs.childNodes:
        if child.nodeType == dom.TEXT_NODE or not child.localName:
            continue

        name = child.localName.lower()

        simple = False
        value = ""
        if (len(child.childNodes) == 1 and
                child.childNodes[0].nodeType == dom.TEXT_NODE):
            simple = True
            value = child.childNodes[0].wholeText

        attrs = dict([(k, v) for k, v in child.attributes.items()])

        # we accept either UserData or CustomData.  If both are present
        # then behavior is undefined.
        if name == "userdata" or name == "customdata":
            if attrs.get('encoding') in (None, "base64"):
                ud = base64.b64decode(''.join(value.split()))
            else:
                ud = value
        elif name == "username":
            username = value
        elif name == "userpassword":
            password = value
        elif name == "hostname":
            md['local-hostname'] = value
        elif name == "dscfg":
            if attrs.get('encoding') in (None, "base64"):
                dscfg = base64.b64decode(''.join(value.split()))
            else:
                dscfg = value
            cfg['datasource'] = {DS_NAME: util.load_yaml(dscfg, default={})}
        elif name == "ssh":
            cfg['_pubkeys'] = load_azure_ovf_pubkeys(child)
        elif name == "disablesshpasswordauthentication":
            cfg['ssh_pwauth'] = util.is_false(value)
        elif simple:
            if name in md_props:
                md[name] = value
            else:
                md['azure_data'][name] = value

    defuser = {}
    if username:
        defuser['name'] = username
    if password:
        defuser['passwd'] = encrypt_pass(password)
        defuser['lock_passwd'] = False

    if defuser:
        cfg['system_info'] = {'default_user': defuser}

    if 'ssh_pwauth' not in cfg and password:
        cfg['ssh_pwauth'] = True

    return (md, ud, cfg)


def encrypt_pass(password, salt_id="$6$"):
    return crypt.crypt(password, salt_id + util.rand_str(strlen=16))


def list_possible_azure_ds_devs():
    # return a sorted list of devices that might have a azure datasource
    devlist = []
    for fstype in ("iso9660", "udf"):
        devlist.extend(util.find_devs_with("TYPE=%s" % fstype))

    devlist.sort(reverse=True)
    return devlist


def load_azure_ds_dir(source_dir):
    ovf_file = os.path.join(source_dir, "ovf-env.xml")

    if not os.path.isfile(ovf_file):
        raise NonAzureDataSource("No ovf-env file found")

    with open(ovf_file, "rb") as fp:
        contents = fp.read()

    md, ud, cfg = read_azure_ovf(contents)
    return (md, ud, cfg, {'ovf-env.xml': contents})


def iid_from_shared_config(path):
    with open(path, "rb") as fp:
        content = fp.read()
    return iid_from_shared_config_content(content)


def iid_from_shared_config_content(content):
    """
    find INSTANCE_ID in:
    <?xml version="1.0" encoding="utf-8"?>
    <SharedConfig version="1.0.0.0" goalStateIncarnation="1">
      <Deployment name="INSTANCE_ID" guid="{...}" incarnation="0">
        <Service name="..." guid="{00000000-0000-0000-0000-000000000000}" />
    """
    dom = minidom.parseString(content)
    depnode = single_node_at_path(dom, ["SharedConfig", "Deployment"])
    return depnode.attributes.get('name').value


class BrokenAzureDataSource(Exception):
    pass


class NonAzureDataSource(Exception):
    pass


# Used to match classes to dependencies
datasources = [
  (DataSourceAzureNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
