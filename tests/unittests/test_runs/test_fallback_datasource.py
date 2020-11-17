import copy
import os
import re
import json
from cloudinit.sources import DataSourceConfigDrive as dscd
from cloudinit.sources import DataSourceOpenStack as dsos
from cloudinit.sources import DataSourceOVF as dsovf
from cloudinit import helpers
from cloudinit.tests import helpers as tests_helpers
from cloudinit.tests.helpers import mock
from cloudinit import util
from cloudinit.tests.helpers import populate_dir
from cloudinit.sources.helpers import openstack
from cloudinit import stages
from cloudinit import safeyaml
import httpretty as hp
from cloudinit import settings
from io import StringIO
from urllib.parse import urlparse


OSTACK_META = {
    'availability_zone': 'nova',
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c'}


OS_FILES = {
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META),
    'openstack/latest/network_data.json': json.dumps(
        {'links': [], 'networks': [], 'services': []}),
}


OVF_ENV_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<Environment xmlns="http://schemas.dmtf.org/ovf/environment/1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:oe="http://schemas.dmtf.org/ovf/environment/1"
  xsi:schemaLocation="http://schemas.dmtf.org/ovf/environment/1 ../dsp8027.xsd"
  oe:id="WebTier">
  <!-- Information about hypervisor platform -->
  <oe:PlatformSection>
      <Kind>ESX Server</Kind>
      <Version>3.0.1</Version>
      <Vendor>VMware, Inc.</Vendor>
      <Locale>en_US</Locale>
  </oe:PlatformSection>
  <!--- Properties defined for this virtual machine -->
  <PropertySection>
{properties}
  </PropertySection>
</Environment>
"""

CFG_DRIVE_FILES_V2 = {
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META)}

BASE_URL = "http://169.254.169.254"


def fill_properties(props, template=OVF_ENV_CONTENT):
    lines = []
    prop_tmpl = '<Property oe:key="{key}" oe:value="{val}"/>'
    for key, val in props.items():
        lines.append(prop_tmpl.format(key=key, val=val))
    indent = "        "
    properties = ''.join([indent + line + "\n" for line in lines])
    return template.format(properties=properties)


def _register_uris(version, ec2_files, ec2_meta, os_files):
    """Registers a set of url patterns into httpretty that will mimic the
    same data returned by the openstack metadata service (and ec2 service)."""

    def match_ec2_url(uri, headers):
        path = uri.path.strip("/")
        if len(path) == 0:
            return (200, headers, "\n".join(EC2_VERSIONS))
        path = uri.path.lstrip("/")
        if path in ec2_files:
            return (200, headers, ec2_files.get(path))
        if path == 'latest/meta-data/':
            buf = StringIO()
            for (k, v) in ec2_meta.items():
                if isinstance(v, (list, tuple)):
                    buf.write("%s/" % (k))
                else:
                    buf.write("%s" % (k))
                buf.write("\n")
            return (200, headers, buf.getvalue())
        if path.startswith('latest/meta-data/'):
            value = None
            pieces = path.split("/")
            if path.endswith("/"):
                pieces = pieces[2:-1]
                value = util.get_cfg_by_path(ec2_meta, pieces)
            else:
                pieces = pieces[2:]
                value = util.get_cfg_by_path(ec2_meta, pieces)
            if value is not None:
                return (200, headers, str(value))
        return (404, headers, '')

    def match_os_uri(uri, headers):
        path = uri.path.strip("/")
        if path == 'openstack':
            return (200, headers, "\n".join([openstack.OS_LATEST]))
        path = uri.path.lstrip("/")
        if path in os_files:
            return (200, headers, os_files.get(path))
        return (404, headers, '')

    def get_request_callback(method, uri, headers):
        uri = urlparse(uri)
        path = uri.path.lstrip("/").split("/")
        if path[0] == 'openstack':
            return match_os_uri(uri, headers)
        return match_ec2_url(uri, headers)

    hp.register_uri(hp.GET, re.compile(r'http://169.254.169.254/.*'),
                    body=get_request_callback)


class TestFallbackDatasource(tests_helpers.FilesystemMockingTestCase,
                             tests_helpers.HttprettyTestCase):
    VERSION = 'latest'

    def setUp(self):
        super(TestFallbackDatasource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})
        self.ds = dscd.DataSourceConfigDrive

    def cloud_init(self, initer):
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        iid = initer.instancify()
        initer.update()
        return iid

    def remove_seed_dir(self, seed_dir):
        self.patched_funcs.close()
        util.del_dir(seed_dir)
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))
        util.del_file(os.path.join(self.tmp, ".instance-id"))

    def test_invalid_config_drive(self):
        seed_dir = os.path.join(self.paths.seed_dir, "config_drive")
        populate_dir(seed_dir, CFG_DRIVE_FILES_V2)

        sys_cfg = {
            'datasource_list': ['ConfigDrive'],
            'datasource': {'ConfigDrive': {'dsmode': 'local'}}
        }

        cloud_cfg = safeyaml.dumps(sys_cfg)
        util.ensure_dir(os.path.join(self.tmp, 'etc', 'cloud'))
        util.write_file(os.path.join(self.tmp, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        dsrc = self.ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        ret = dsrc.get_data()
        self.assertEqual(
            dsrc.subplatform, 'seed-dir (%s)' % seed_dir)
        self.assertTrue(ret)
        # simulate first boot with config drive
        self.reRoot(self.tmp)
        initer = stages.Init()
        initer.datasource = dsrc
        iid_with_dsrc = self.cloud_init(initer)
        # simulate subsequent boot without config drive
        self.remove_seed_dir(seed_dir)
        self.reRoot(self.tmp)
        initer = stages.Init(ds_deps=['FILESYSTEM'])
        iid_without_dsrc = self.cloud_init(initer)
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)

    def test_invalid_openstack_uri(self):
        _register_uris(self.VERSION, {}, {}, OS_FILES)
        sys_cfg = {
            'datasource_list': ['OpenStack'],
            'datasource': {'OpenStack': {'dsmode': 'net'}}
        }
        cloud_cfg = safeyaml.dumps(sys_cfg)
        util.ensure_dir(os.path.join(self.tmp, 'etc', 'cloud'))
        util.write_file(os.path.join(self.tmp, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        self.ds = dsos.DataSourceOpenStack
        ds_os = self.ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
        MOCK_PATH = 'cloudinit.sources.DataSourceOpenStack.'
        mock_path = MOCK_PATH + 'detect_openstack'
        with tests_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        self.assertTrue(found)
        self.reRoot(self.tmp)
        # simulate first boot with datasource openstack
        initer = stages.Init()
        initer.datasource = ds_os
        iid_with_dsrc = self.cloud_init(initer)

        # simulate subsequent boot without datasource openstack
        util.del_file(os.path.join(self.tmp, "run/cloud-init/.instance-id"))
        hp.register_uri(hp.GET, re.compile(r'http://169.254.169.254/.*'),
                        status=504)
        self.reRoot(self.tmp)
        initer = stages.Init()
        iid_without_dsrc = self.cloud_init(initer)
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)

    def test_invalid_ovf(self):
        self.ds = dsovf.DataSourceOVF
        props = {"password": "passw0rd", "instance-id": "inst-001"}
        env = fill_properties(props)
        ovf_env = self.tmp_path('ovf-env.xml', dir=self.paths.seed_dir)
        util.write_file(ovf_env, env)
        dsrc = self.ds(sys_cfg={}, distro=None, paths=self.paths)
        MPATH = 'cloudinit.sources.DataSourceOVF.'
        with mock.patch(MPATH + 'util.read_dmi_data', return_value='!VMware'):
            with mock.patch(MPATH + 'transport_vmware_guestinfo') as m_guestd:
                with mock.patch(MPATH + 'transport_iso9660') as m_iso9660:
                    m_iso9660.return_value = None
                    m_guestd.return_value = None
                    self.assertTrue(dsrc.get_data())

        self.reRoot(self.tmp)
        # simulate first boot with datasource OVF
        initer = stages.Init()
        initer.datasource = dsrc
        iid_with_dsrc = self.cloud_init(initer)
        # simulate subsequent boot without datasource OVF
        self.remove_seed_dir(self.paths.seed_dir)
        self.reRoot(self.tmp)
        initer = stages.Init(ds_deps=['FILESYSTEM'])
        iid_without_dsrc = self.cloud_init(initer)
        self.assertEqual(iid_with_dsrc, iid_without_dsrc)
