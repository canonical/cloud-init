# Copyright (C) 2013 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import contextlib
import crypt
from functools import partial
import os
import os.path
import time
from xml.dom import minidom
import xml.etree.ElementTree as ET

from cloudinit import log as logging
from cloudinit import sources
from cloudinit.sources.helpers.azure import get_metadata_from_fabric
from cloudinit import util

LOG = logging.getLogger(__name__)

DS_NAME = 'Azure'
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}
AGENT_START = ['service', 'walinuxagent', 'start']
AGENT_START_BUILTIN = "__builtin__"
BOUNCE_COMMAND = [
    'sh', '-xc',
    "i=$interface; x=0; ifdown $i || x=$?; ifup $i || x=$?; exit $x"
]
# azure systems will always have a resource disk, and 66-azure-ephemeral.rules
# ensures that it gets linked to this path.
RESOURCE_DISK_PATH = '/dev/disk/cloud/azure_resource'

BUILTIN_DS_CONFIG = {
    'agent_command': AGENT_START_BUILTIN,
    'data_dir': "/var/lib/waagent",
    'set_hostname': True,
    'hostname_bounce': {
        'interface': 'eth0',
        'policy': True,
        'command': BOUNCE_COMMAND,
        'hostname_command': 'hostname',
    },
    'disk_aliases': {'ephemeral0': RESOURCE_DISK_PATH},
    'dhclient_lease_file': '/var/lib/dhcp/dhclient.eth0.leases',
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

# The redacted password fails to meet password complexity requirements
# so we can safely use this to mask/redact the password in the ovf-env.xml
DEF_PASSWD_REDACTION = 'REDACTED'


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
    if (not util.is_true(cfg.get('set_hostname')) or
       util.is_false(policy) or
       (previous_hostname == temp_hostname and policy != 'force')):
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
        self.dhclient_lease_file = self.ds_cfg.get('dhclient_lease_file')

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_metadata_from_agent(self):
        temp_hostname = self.metadata.get('local-hostname')
        hostname_command = self.ds_cfg['hostname_bounce']['hostname_command']
        agent_cmd = self.ds_cfg['agent_command']
        LOG.debug("Getting metadata via agent.  hostname=%s cmd=%s",
                  temp_hostname, agent_cmd)
        with temporary_hostname(temp_hostname, self.ds_cfg,
                                hostname_command=hostname_command) \
                as previous_hostname:
            if (previous_hostname is not None and
               util.is_true(self.ds_cfg.get('set_hostname'))):
                cfg = self.ds_cfg['hostname_bounce']
                try:
                    perform_hostname_bounce(hostname=temp_hostname,
                                            cfg=cfg,
                                            prev_hostname=previous_hostname)
                except Exception as e:
                    LOG.warn("Failed publishing hostname: %s", e)
                    util.logexc(LOG, "handling set_hostname failed")

            try:
                invoke_agent(agent_cmd)
            except util.ProcessExecutionError:
                # claim the datasource even if the command failed
                util.logexc(LOG, "agent command '%s' failed.",
                            self.ds_cfg['agent_command'])

            ddir = self.ds_cfg['data_dir']

            fp_files = []
            key_value = None
            for pk in self.cfg.get('_pubkeys', []):
                if pk.get('value', None):
                    key_value = pk['value']
                    LOG.debug("ssh authentication: using value from fabric")
                else:
                    bname = str(pk['fingerprint'] + ".crt")
                    fp_files += [os.path.join(ddir, bname)]
                    LOG.debug("ssh authentication: "
                              "using fingerprint from fabirc")

            missing = util.log_time(logfunc=LOG.debug, msg="waiting for files",
                                    func=wait_for_files,
                                    args=(fp_files,))
        if len(missing):
            LOG.warn("Did not find files, but going on: %s", missing)

        metadata = {}
        metadata['public-keys'] = key_value or pubkeys_from_crt_files(fp_files)
        return metadata

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

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(ddir, files, dirmode=0o700)

        if self.ds_cfg['agent_command'] == AGENT_START_BUILTIN:
            metadata_func = partial(get_metadata_from_fabric,
                                    fallback_lease_file=self.
                                    dhclient_lease_file)
        else:
            metadata_func = self.get_metadata_from_agent

        try:
            fabric_data = metadata_func()
        except Exception as exc:
            LOG.info("Error communicating with Azure fabric; assume we aren't"
                     " on Azure.", exc_info=True)
            return False
        self.metadata['instance-id'] = util.read_dmi_data('system-uuid')
        self.metadata.update(fabric_data)

        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    def activate(self, cfg, is_new_instance):
        address_ephemeral_resize(is_new_instance=is_new_instance)
        return


def can_dev_be_reformatted(devpath):
    # determine if the ephemeral block device path devpath
    # is newly formatted after a resize.
    if not os.path.exists(devpath):
        return False, 'device %s does not exist' % devpath

    realpath = os.path.realpath(devpath)
    LOG.debug('Resolving realpath of %s -> %s', devpath, realpath)

    # it is possible that the block device might exist, but the kernel
    # have not yet read the partition table and sent events.  we udevadm settle
    # to hope to resolve that.  Better here would probably be to test and see,
    # and then settle if we didn't find anything and try again.
    if util.which("udevadm"):
        util.subp(["udevadm", "settle"])

    # devpath of /dev/sd[a-z] or /dev/disk/cloud/azure_resource
    # where partitions are "<devpath>1" or "<devpath>-part1" or "<devpath>p1"
    part1path = None
    for suff in ("-part", "p", ""):
        cand = devpath + suff + "1"
        if os.path.exists(cand):
            if os.path.exists(devpath + suff + "2"):
                msg = ('device %s had more than 1 partition: %s, %s' %
                       devpath, cand, devpath + suff + "2")
                return False, msg
            part1path = cand
            break

    if part1path is None:
        return False, 'device %s was not partitioned' % devpath

    real_part1path = os.path.realpath(part1path)
    ntfs_devices = util.find_devs_with("TYPE=ntfs", no_cache=True)
    LOG.debug('ntfs_devices found = %s', ntfs_devices)
    if real_part1path not in ntfs_devices:
        msg = ('partition 1 (%s -> %s) on device %s was not ntfs formatted' %
               (part1path, real_part1path, devpath))
        return False, msg

    def count_files(mp):
        ignored = set(['dataloss_warning_readme.txt'])
        return len([f for f in os.listdir(mp) if f.lower() not in ignored])

    bmsg = ('partition 1 (%s -> %s) on device %s was ntfs formatted' %
            (part1path, real_part1path, devpath))
    try:
        file_count = util.mount_cb(part1path, count_files)
    except util.MountFailedError as e:
        return False, bmsg + ' but mount of %s failed: %s' % (part1path, e)

    if file_count != 0:
        return False, bmsg + ' but had %d files on it.' % file_count

    return True, bmsg + ' and had no important files. Safe for reformatting.'


def address_ephemeral_resize(devpath=RESOURCE_DISK_PATH, maxwait=120,
                             is_new_instance=False):
    # wait for ephemeral disk to come up
    naplen = .2
    missing = wait_for_files([devpath], maxwait=maxwait, naplen=naplen,
                             log_pre="Azure ephemeral disk: ")

    if missing:
        LOG.warn("ephemeral device '%s' did not appear after %d seconds.",
                 devpath, maxwait)
        return

    result = False
    msg = None
    if is_new_instance:
        result, msg = (True, "First instance boot.")
    else:
        result, msg = can_dev_be_reformatted(devpath)

    LOG.debug("reformattable=%s: %s" % (result, msg))
    if not result:
        return

    for mod in ['disk_setup', 'mounts']:
        sempath = '/var/lib/cloud/instance/sem/config_' + mod
        bmsg = 'Marker "%s" for module "%s"' % (sempath, mod)
        if os.path.exists(sempath):
            try:
                os.unlink(sempath)
                LOG.debug(bmsg + " removed.")
            except Exception as e:
                # python3 throws FileNotFoundError, python2 throws OSError
                LOG.warn(bmsg + ": remove failed! (%s)" % e)
        else:
            LOG.debug(bmsg + " did not exist.")
    return


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


def wait_for_files(flist, maxwait=60, naplen=.5, log_pre=""):
    need = set(flist)
    waited = 0
    while True:
        need -= set([f for f in need if os.path.exists(f)])
        if len(need) == 0:
            LOG.debug("%sAll files appeared after %s seconds: %s",
                      log_pre, waited, flist)
            return []
        if waited == 0:
            LOG.info("%sWaiting up to %s seconds for the following files: %s",
                     log_pre, maxwait, flist)
        if waited + naplen > maxwait:
            break
        time.sleep(naplen)
        waited += naplen

    LOG.warn("%sStill missing files after %s seconds: %s",
             log_pre, maxwait, need)
    return need


def write_files(datadir, files, dirmode=None):

    def _redact_password(cnt, fname):
        """Azure provides the UserPassword in plain text. So we redact it"""
        try:
            root = ET.fromstring(cnt)
            for elem in root.iter():
                if ('UserPassword' in elem.tag and
                   elem.text != DEF_PASSWD_REDACTION):
                    elem.text = DEF_PASSWD_REDACTION
            return ET.tostring(root)
        except Exception:
            LOG.critical("failed to redact userpassword in %s", fname)
            return cnt

    if not datadir:
        return
    if not files:
        files = {}
    util.ensure_dir(datadir, dirmode)
    for (name, content) in files.items():
        fname = os.path.join(datadir, name)
        if 'ovf-env.xml' in name:
            content = _redact_password(content, fname)
        util.write_file(filename=fname, content=content, mode=0o600)


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

        cur = {'fingerprint': "", 'path': "", 'value': ""}
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
                            lambda n:
                            n.localName == "LinuxProvisioningConfigurationSet")

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
    if password and DEF_PASSWD_REDACTION != password:
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

# vi: ts=4 expandtab
