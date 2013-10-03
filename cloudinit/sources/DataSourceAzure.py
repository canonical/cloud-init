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
import crypt
import os
import os.path
import time
from xml.dom import minidom

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DS_NAME = 'Azure'
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}
AGENT_START = ['service', 'walinuxagent', 'start']
BOUNCE_COMMAND = ['sh', '-xc',
    "i=$interface; x=0; ifdown $i || x=$?; ifup $i || x=$?; exit $x"]

BUILTIN_DS_CONFIG = {
    'agent_command': AGENT_START,
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
        'ephemeral0': {'table_type': 'mbr',
                       'layout': True,
                       'overwrite': False}
         },
    'fs_setup': [{'filesystem': 'ext4',
                  'device': 'ephemeral0.1',
                  'replace_fs': 'ntfs'}]
}

DS_CFG_PATH = ['datasource', DS_NAME]


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
                LOG.warn("%s was not mountable" % cdev)
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
        seed = util.load_file("/sys/firmware/acpi/tables/OEM0", quiet=True)
        if seed:
            self.metadata['random_seed'] = seed

        # now update ds_cfg to reflect contents pass in config
        user_ds_cfg = util.get_cfg_by_path(self.cfg, DS_CFG_PATH, {})
        self.ds_cfg = util.mergemanydict([user_ds_cfg, self.ds_cfg])
        mycfg = self.ds_cfg

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(mycfg['data_dir'], files, dirmode=0700)

        # handle the hostname 'publishing'
        try:
            handle_set_hostname(mycfg.get('set_hostname'),
                                self.metadata.get('local-hostname'),
                                mycfg['hostname_bounce'])
        except Exception as e:
            LOG.warn("Failed publishing hostname: %s" % e)
            util.logexc(LOG, "handling set_hostname failed")

        try:
            invoke_agent(mycfg['agent_command'])
        except util.ProcessExecutionError:
            # claim the datasource even if the command failed
            util.logexc(LOG, "agent command '%s' failed.",
                        mycfg['agent_command'])

        shcfgxml = os.path.join(mycfg['data_dir'], "SharedConfig.xml")
        wait_for = [shcfgxml]

        fp_files = []
        for pk in self.cfg.get('_pubkeys', []):
            bname = pk['fingerprint'] + ".crt"
            fp_files += [os.path.join(mycfg['data_dir'], bname)]

        missing = util.log_time(logfunc=LOG.debug, msg="waiting for files",
                                func=wait_for_files,
                                args=(wait_for + fp_files,))
        if len(missing):
            LOG.warn("Did not find files, but going on: %s", missing)

        if shcfgxml in missing:
            LOG.warn("SharedConfig.xml missing, using static instance-id")
        else:
            try:
                self.metadata['instance-id'] = iid_from_shared_config(shcfgxml)
            except ValueError as e:
                LOG.warn("failed to get instance id in %s: %s" % (shcfgxml, e))

        pubkeys = pubkeys_from_crt_files(fp_files)

        self.metadata['public-keys'] = pubkeys
        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg


def handle_set_hostname(enabled, hostname, cfg):
    if not util.is_true(enabled):
        return

    if not hostname:
        LOG.warn("set_hostname was true but no local-hostname")
        return

    apply_hostname_bounce(hostname=hostname, policy=cfg['policy'],
                          interface=cfg['interface'],
                          command=cfg['command'],
                          hostname_command=cfg['hostname_command'])


def apply_hostname_bounce(hostname, policy, interface, command,
                          hostname_command="hostname"):
    # set the hostname to 'hostname' if it is not already set to that.
    # then, if policy is not off, bounce the interface using command
    prev_hostname = util.subp(hostname_command, capture=True)[0].strip()

    util.subp([hostname_command, hostname])

    msg = ("phostname=%s hostname=%s policy=%s interface=%s" %
           (prev_hostname, hostname, policy, interface))

    if util.is_false(policy):
        LOG.debug("pubhname: policy false, skipping [%s]", msg)
        return

    if prev_hostname == hostname and policy != "force":
        LOG.debug("pubhname: no change, policy != force. skipping. [%s]", msg)
        return

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


def crtfile_to_pubkey(fname):
    pipeline = ('openssl x509 -noout -pubkey < "$0" |'
                'ssh-keygen -i -m PKCS8 -f /dev/stdin')
    (out, _err) = util.subp(['sh', '-c', pipeline, fname], capture=True)
    return out.rstrip()


def pubkeys_from_crt_files(flist):
    pubkeys = []
    errors = []
    for fname in flist:
        try:
            pubkeys.append(crtfile_to_pubkey(fname))
        except util.ProcessExecutionError:
            errors.extend(fname)

    if errors:
        LOG.warn("failed to convert the crt files to pubkey: %s" % errors)

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
                        content=content, mode=0600)


def invoke_agent(cmd):
    # this is a function itself to simplify patching it for test
    if cmd:
        LOG.debug("invoking agent: %s" % cmd)
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
            if (child.nodeType == text_node or not child.localName):
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

        attrs = {k: v for k, v in child.attributes.items()}

        # we accept either UserData or CustomData.  If both are present
        # then behavior is undefined.
        if (name == "userdata" or name == "customdata"):
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

    with open(ovf_file, "r") as fp:
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
