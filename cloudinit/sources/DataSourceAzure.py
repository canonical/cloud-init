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
from xml.dom import minidom

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DS_NAME = 'Azure'
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}
AGENT_START = ['service', 'walinuxagent', 'start']
DEFAULT_DS_CONFIG = {'datasource': {DS_NAME: {'agent_command': AGENT_START}}}


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
        candidates = [self.seed_dir]
        candidates.extend(list_possible_azure_ds_devs())
        found = None

        for cdev in candidates:
            try:
                if cdev.startswith("/dev/"):
                    ret = util.mount_cb(cdev, load_azure_ds_dir)
                else:
                    ret = load_azure_ds_dir(cdev)

            except NonAzureDataSource:
                pass
            except BrokenAzureDataSource as exc:
                raise exc
            except util.MountFailedError:
                LOG.warn("%s was not mountable" % cdev)

            (md, self.userdata_raw, cfg) = ret
            self.seed = cdev
            self.metadata = util.mergemanydict([md, DEFAULT_METADATA])
            self.cfg = util.mergemanydict([cfg, DEFAULT_DS_CONFIG])
            found = cdev

            LOG.debug("found datasource in %s", cdev)
            break

        if not found:
            return False

        path = ['datasource', DS_NAME, 'agent_command']
        cmd = None
        for cfg in (self.cfg, self.sys_cfg):
            cmd = util.get_cfg_by_path(cfg, keyp=path)
            if cmd is not None:
                break
        invoke_agent(cmd)

    def get_config_obj(self):
        return self.cfg


def invoke_agent(cmd):
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


def read_azure_ovf(contents):
    dom = minidom.parseString(contents)
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

    for child in lpcs.childNodes:
        if child.nodeType == dom.TEXT_NODE or not child.localName:
            continue

        name = child.localName.lower()

        simple = False
        if (len(child.childNodes) == 1 and
            child.childNodes[0].nodeType == dom.TEXT_NODE):
            simple = True
            value = child.childNodes[0].wholeText

        if name == "userdata":
            ud = base64.b64decode(''.join(value.split()))
        elif name == "username":
            cfg['system_info'] = {'default_user': {'name': value}}
        elif name == "hostname":
            md['local-hostname'] = value
        elif name == "dscfg":
            cfg['datasource'] = {DS_NAME: util.load_yaml(value, default={})}
        elif simple:
            if name in md_props:
                md[name] = value
            else:
                md['azure_data'][name] = value

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

    return read_azure_ovf(contents)


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
