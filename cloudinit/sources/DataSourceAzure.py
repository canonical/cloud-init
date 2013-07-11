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
BUILTIN_DS_CONFIG = {'datasource': {DS_NAME: {
     'agent_command': AGENT_START,
     'data_dir': "/var/lib/waagent"}}}


class DataSourceAzureNet(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'azure')
        self.cfg = {}
        self.seed = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        ddir_cfgpath = ['datasource', DS_NAME, 'data_dir']
        # azure removes/ejects the cdrom containing the ovf-env.xml
        # file on reboot.  So, in order to successfully reboot we
        # need to look in the datadir and consider that valid
        ddir = util.get_cfg_by_path(self.sys_cfg, ddir_cfgpath)
        if ddir is None:
            ddir = util.get_cfg_by_path(BUILTIN_DS_CONFIG, ddir_cfgpath)

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
            self.cfg = cfg
            found = cdev

            LOG.debug("found datasource in %s", cdev)
            break

        if not found:
            return False

        if found == ddir:
            LOG.debug("using cached datasource in %s", ddir)

        fields = [('cmd', ['datasource', DS_NAME, 'agent_command']),
                  ('datadir', ddir_cfgpath)]
        mycfg = {}
        for cfg in (self.cfg, self.sys_cfg, BUILTIN_DS_CONFIG):
            for name, path in fields:
                if name in mycfg:
                    continue
                value = util.get_cfg_by_path(cfg, keyp=path)
                if value is not None:
                    mycfg[name] = value

        write_files(mycfg['datadir'], files)

        try:
            invoke_agent(mycfg['cmd'])
        except util.ProcessExecutionError:
            # claim the datasource even if the command failed
            util.logexc(LOG, "agent command '%s' failed.", mycfg['cmd'])

        wait_for = [os.path.join(mycfg['datadir'], "SharedConfig.xml")]

        fp_files = []
        for pk in self.cfg.get('_pubkeys', []):
            bname = pk['fingerprint'] + ".crt"
            fp_files += [os.path.join(mycfg['datadir'], bname)]

        start = time.time()
        missing = wait_for_files(wait_for + fp_files)
        if len(missing):
            LOG.warn("Did not find files, but going on: %s", missing)
        else:
            LOG.debug("waited %.3f seconds for %d files to appear",
                      time.time() - start, len(wait_for))

        pubkeys = pubkeys_from_crt_files(fp_files)

        self.metadata['public-keys'] = pubkeys

        return True

    def get_config_obj(self):
        return self.cfg


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


def write_files(datadir, files):
    if not datadir:
        return
    if not files:
        files = {}
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


def read_azure_ovf(contents):
    try:
        dom = minidom.parseString(contents)
    except Exception as e:
        raise NonAzureDataSource("invalid xml: %s" % e)

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
        if (len(child.childNodes) == 1 and
            child.childNodes[0].nodeType == dom.TEXT_NODE):
            simple = True
            value = child.childNodes[0].wholeText

        # we accept either UserData or CustomData.  If both are present
        # then behavior is undefined.
        if (name == "userdata" or name == "customdata"):
            ud = base64.b64decode(''.join(value.split()))
        elif name == "username":
            username = value
        elif name == "userpassword":
            password = value
        elif name == "hostname":
            md['local-hostname'] = value
        elif name == "dscfg":
            cfg['datasource'] = {DS_NAME: util.load_yaml(value, default={})}
        elif name == "ssh":
            cfg['_pubkeys'] = load_azure_ovf_pubkeys(child)
        elif name == "disablesshpasswordauthentication":
            cfg['ssh_pwauth'] = util.is_true(value)
        elif simple:
            if name in md_props:
                md[name] = value
            else:
                md['azure_data'][name] = value

    defuser = {}
    if username:
        defuser['name'] = username
    if password:
        defuser['password'] = password
        defuser['lock_passwd'] = False

    if defuser:
        cfg['system_info'] = {'default_user': defuser}

    if 'ssh_pwauth' not in cfg and password:
        cfg['ssh_pwauth'] = True

    return (md, ud, cfg)


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
