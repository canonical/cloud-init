from cloudinit import helpers
from cloudinit.util import b64e, decode_binary, load_file
from cloudinit.sources import DataSourceAzure
from ..helpers import TestCase, populate_dir

try:
    from unittest import mock
except ImportError:
    import mock
try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

import crypt
import os
import stat
import struct
import yaml
import shutil
import tempfile
import unittest

from cloudinit import url_helper


GOAL_STATE_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<GoalState xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="goalstate10.xsd">
  <Version>2012-11-30</Version>
  <Incarnation>{incarnation}</Incarnation>
  <Machine>
    <ExpectedState>Started</ExpectedState>
    <StopRolesDeadlineHint>300000</StopRolesDeadlineHint>
    <LBProbePorts>
      <Port>16001</Port>
    </LBProbePorts>
    <ExpectHealthReport>FALSE</ExpectHealthReport>
  </Machine>
  <Container>
    <ContainerId>{container_id}</ContainerId>
    <RoleInstanceList>
      <RoleInstance>
        <InstanceId>{instance_id}</InstanceId>
        <State>Started</State>
        <Configuration>
          <HostingEnvironmentConfig>http://100.86.192.70:80/machine/46504ebc-f968-4f23-b9aa-cd2b3e4d470c/68ce47b32ea94952be7b20951c383628.utl%2Dtrusty%2D%2D292258?comp=config&amp;type=hostingEnvironmentConfig&amp;incarnation=1</HostingEnvironmentConfig>
          <SharedConfig>{shared_config_url}</SharedConfig>
          <ExtensionsConfig>http://100.86.192.70:80/machine/46504ebc-f968-4f23-b9aa-cd2b3e4d470c/68ce47b32ea94952be7b20951c383628.utl%2Dtrusty%2D%2D292258?comp=config&amp;type=extensionsConfig&amp;incarnation=1</ExtensionsConfig>
          <FullConfig>http://100.86.192.70:80/machine/46504ebc-f968-4f23-b9aa-cd2b3e4d470c/68ce47b32ea94952be7b20951c383628.utl%2Dtrusty%2D%2D292258?comp=config&amp;type=fullConfig&amp;incarnation=1</FullConfig>
          <Certificates>{certificates_url}</Certificates>
          <ConfigName>68ce47b32ea94952be7b20951c383628.0.68ce47b32ea94952be7b20951c383628.0.utl-trusty--292258.1.xml</ConfigName>
        </Configuration>
      </RoleInstance>
    </RoleInstanceList>
  </Container>
</GoalState>
"""


def construct_valid_ovf_env(data=None, pubkeys=None, userdata=None):
    if data is None:
        data = {'HostName': 'FOOHOST'}
    if pubkeys is None:
        pubkeys = {}

    content = """<?xml version="1.0" encoding="utf-8"?>
<Environment xmlns="http://schemas.dmtf.org/ovf/environment/1"
 xmlns:oe="http://schemas.dmtf.org/ovf/environment/1"
 xmlns:wa="http://schemas.microsoft.com/windowsazure"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

 <wa:ProvisioningSection><wa:Version>1.0</wa:Version>
 <LinuxProvisioningConfigurationSet
  xmlns="http://schemas.microsoft.com/windowsazure"
  xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <ConfigurationSetType>LinuxProvisioningConfiguration</ConfigurationSetType>
    """
    for key, dval in data.items():
        if isinstance(dval, dict):
            val = dval.get('text')
            attrs = ' ' + ' '.join(["%s='%s'" % (k, v) for k, v in dval.items()
                                    if k != 'text'])
        else:
            val = dval
            attrs = ""
        content += "<%s%s>%s</%s>\n" % (key, attrs, val, key)

    if userdata:
        content += "<UserData>%s</UserData>\n" % (b64e(userdata))

    if pubkeys:
        content += "<SSH><PublicKeys>\n"
        for fp, path in pubkeys:
            content += " <PublicKey>"
            content += ("<Fingerprint>%s</Fingerprint><Path>%s</Path>" %
                        (fp, path))
            content += "</PublicKey>\n"
        content += "</PublicKeys></SSH>"
    content += """
 </LinuxProvisioningConfigurationSet>
 </wa:ProvisioningSection>
 <wa:PlatformSettingsSection><wa:Version>1.0</wa:Version>
 <PlatformSettings xmlns="http://schemas.microsoft.com/windowsazure"
  xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
 <KmsServerHostname>kms.core.windows.net</KmsServerHostname>
 <ProvisionGuestAgent>false</ProvisionGuestAgent>
 <GuestAgentPackageName i:nil="true" />
 </PlatformSettings></wa:PlatformSettingsSection>
</Environment>
    """

    return content


class TestAzureDataSource(TestCase):

    def setUp(self):
        super(TestAzureDataSource, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        self.paths = helpers.Paths({'cloud_dir': self.tmp})
        self.waagent_d = os.path.join(self.tmp, 'var', 'lib', 'waagent')

        self.patches = ExitStack()
        self.addCleanup(self.patches.close)

        super(TestAzureDataSource, self).setUp()

    def apply_patches(self, patches):
        for module, name, new in patches:
            self.patches.enter_context(mock.patch.object(module, name, new))

    def _get_ds(self, data):

        def dsdevs():
            return data.get('dsdevs', [])

        def _invoke_agent(cmd):
            data['agent_invoked'] = cmd

        def _wait_for_files(flist, _maxwait=None, _naplen=None):
            data['waited'] = flist
            return []

        def _pubkeys_from_crt_files(flist):
            data['pubkey_files'] = flist
            return ["pubkey_from: %s" % f for f in flist]

        def _iid_from_shared_config(path):
            data['iid_from_shared_cfg'] = path
            return 'i-my-azure-id'

        if data.get('ovfcontent') is not None:
            populate_dir(os.path.join(self.paths.seed_dir, "azure"),
                         {'ovf-env.xml': data['ovfcontent']})

        mod = DataSourceAzure
        mod.BUILTIN_DS_CONFIG['data_dir'] = self.waagent_d

        fake_shim = mock.MagicMock()
        fake_shim().register_with_azure_and_fetch_data.return_value = {
            'instance-id': 'i-my-azure-id',
            'public-keys': [],
        }

        self.apply_patches([
            (mod, 'list_possible_azure_ds_devs', dsdevs),
            (mod, 'invoke_agent', _invoke_agent),
            (mod, 'wait_for_files', _wait_for_files),
            (mod, 'pubkeys_from_crt_files', _pubkeys_from_crt_files),
            (mod, 'iid_from_shared_config', _iid_from_shared_config),
            (mod, 'perform_hostname_bounce', mock.MagicMock()),
            (mod, 'get_hostname', mock.MagicMock()),
            (mod, 'set_hostname', mock.MagicMock()),
            (mod, 'WALinuxAgentShim', fake_shim),
        ])

        dsrc = mod.DataSourceAzureNet(
            data.get('sys_cfg', {}), distro=None, paths=self.paths)

        return dsrc

    def test_basic_seed_dir(self):
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata),
                'sys_cfg': {}}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, "")
        self.assertEqual(dsrc.metadata['local-hostname'], odata['HostName'])
        self.assertTrue(os.path.isfile(
            os.path.join(self.waagent_d, 'ovf-env.xml')))
        self.assertEqual(dsrc.metadata['instance-id'], 'i-my-azure-id')

    def test_waagent_d_has_0700_perms(self):
        # we expect /var/lib/waagent to be created 0700
        dsrc = self._get_ds({'ovfcontent': construct_valid_ovf_env()})
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue(os.path.isdir(self.waagent_d))
        self.assertEqual(stat.S_IMODE(os.stat(self.waagent_d).st_mode), 0o700)

    def test_user_cfg_set_agent_command_plain(self):
        # set dscfg in via plaintext
        # we must have friendly-to-xml formatted plaintext in yaml_cfg
        # not all plaintext is expected to work.
        yaml_cfg = "{agent_command: my_command}\n"
        cfg = yaml.safe_load(yaml_cfg)
        odata = {'HostName': "myhost", 'UserName': "myuser",
                'dscfg': {'text': yaml_cfg, 'encoding': 'plain'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(data['agent_invoked'], cfg['agent_command'])

    def test_user_cfg_set_agent_command(self):
        # set dscfg in via base64 encoded yaml
        cfg = {'agent_command': "my_command"}
        odata = {'HostName': "myhost", 'UserName': "myuser",
                'dscfg': {'text': b64e(yaml.dump(cfg)),
                          'encoding': 'base64'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(data['agent_invoked'], cfg['agent_command'])

    def test_sys_cfg_set_agent_command(self):
        sys_cfg = {'datasource': {'Azure': {'agent_command': '_COMMAND'}}}
        data = {'ovfcontent': construct_valid_ovf_env(data={}),
                'sys_cfg': sys_cfg}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(data['agent_invoked'], '_COMMAND')

    def test_username_used(self):
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.cfg['system_info']['default_user']['name'],
                         "myuser")

    def test_password_given(self):
        odata = {'HostName': "myhost", 'UserName': "myuser",
                 'UserPassword': "mypass"}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue('default_user' in dsrc.cfg['system_info'])
        defuser = dsrc.cfg['system_info']['default_user']

        # default user should be updated username and should not be locked.
        self.assertEqual(defuser['name'], odata['UserName'])
        self.assertFalse(defuser['lock_passwd'])
        # passwd is crypt formated string $id$salt$encrypted
        # encrypting plaintext with salt value of everything up to final '$'
        # should equal that after the '$'
        pos = defuser['passwd'].rfind("$") + 1
        self.assertEqual(defuser['passwd'],
            crypt.crypt(odata['UserPassword'], defuser['passwd'][0:pos]))

    def test_userdata_plain(self):
        mydata = "FOOBAR"
        odata = {'UserData': {'text': mydata, 'encoding': 'plain'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(decode_binary(dsrc.userdata_raw), mydata)

    def test_userdata_found(self):
        mydata = "FOOBAR"
        odata = {'UserData': {'text': b64e(mydata), 'encoding': 'base64'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, mydata.encode('utf-8'))

    def test_no_datasource_expected(self):
        # no source should be found if no seed_dir and no devs
        data = {}
        dsrc = self._get_ds({})
        ret = dsrc.get_data()
        self.assertFalse(ret)
        self.assertFalse('agent_invoked' in data)

    def test_cfg_has_pubkeys(self):
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        mypklist = [{'fingerprint': 'fp1', 'path': 'path1'}]
        pubkeys = [(x['fingerprint'], x['path']) for x in mypklist]
        data = {'ovfcontent': construct_valid_ovf_env(data=odata,
                                                      pubkeys=pubkeys)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        for mypk in mypklist:
            self.assertIn(mypk, dsrc.cfg['_pubkeys'])

    def test_default_ephemeral(self):
        # make sure the ephemeral device works
        odata = {}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata),
                'sys_cfg': {}}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        cfg = dsrc.get_config_obj()

        self.assertEquals(dsrc.device_name_to_device("ephemeral0"),
                          "/dev/sdb")
        assert 'disk_setup' in cfg
        assert 'fs_setup' in cfg
        self.assertIsInstance(cfg['disk_setup'], dict)
        self.assertIsInstance(cfg['fs_setup'], list)

    def test_provide_disk_aliases(self):
        # Make sure that user can affect disk aliases
        dscfg = {'disk_aliases': {'ephemeral0': '/dev/sdc'}}
        odata = {'HostName': "myhost", 'UserName': "myuser",
                'dscfg': {'text': b64e(yaml.dump(dscfg)),
                          'encoding': 'base64'}}
        usercfg = {'disk_setup': {'/dev/sdc': {'something': '...'},
                                  'ephemeral0': False}}
        userdata = '#cloud-config' + yaml.dump(usercfg) + "\n"

        ovfcontent = construct_valid_ovf_env(data=odata, userdata=userdata)
        data = {'ovfcontent': ovfcontent, 'sys_cfg': {}}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        cfg = dsrc.get_config_obj()
        self.assertTrue(cfg)

    def test_userdata_arrives(self):
        userdata = "This is my user-data"
        xml = construct_valid_ovf_env(data={}, userdata=userdata)
        data = {'ovfcontent': xml}
        dsrc = self._get_ds(data)
        dsrc.get_data()

        self.assertEqual(userdata.encode('us-ascii'), dsrc.userdata_raw)

    def test_ovf_env_arrives_in_waagent_dir(self):
        xml = construct_valid_ovf_env(data={}, userdata="FOODATA")
        dsrc = self._get_ds({'ovfcontent': xml})
        dsrc.get_data()

        # 'data_dir' is '/var/lib/waagent' (walinux-agent's state dir)
        # we expect that the ovf-env.xml file is copied there.
        ovf_env_path = os.path.join(self.waagent_d, 'ovf-env.xml')
        self.assertTrue(os.path.exists(ovf_env_path))
        self.assertEqual(xml, load_file(ovf_env_path))

    def test_ovf_can_include_unicode(self):
        xml = construct_valid_ovf_env(data={})
        xml = u'\ufeff{0}'.format(xml)
        dsrc = self._get_ds({'ovfcontent': xml})
        dsrc.get_data()

    def test_existing_ovf_same(self):
        # waagent/SharedConfig left alone if found ovf-env.xml same as cached
        odata = {'UserData': b64e("SOMEUSERDATA")}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        populate_dir(self.waagent_d,
            {'ovf-env.xml': data['ovfcontent'],
             'otherfile': 'otherfile-content',
             'SharedConfig.xml': 'mysharedconfig'})

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue(os.path.exists(
            os.path.join(self.waagent_d, 'ovf-env.xml')))
        self.assertTrue(os.path.exists(
            os.path.join(self.waagent_d, 'otherfile')))
        self.assertTrue(os.path.exists(
            os.path.join(self.waagent_d, 'SharedConfig.xml')))

    def test_existing_ovf_diff(self):
        # waagent/SharedConfig must be removed if ovfenv is found elsewhere

        # 'get_data' should remove SharedConfig.xml in /var/lib/waagent
        # if ovf-env.xml differs.
        cached_ovfenv = construct_valid_ovf_env(
            {'userdata': b64e("FOO_USERDATA")})
        new_ovfenv = construct_valid_ovf_env(
            {'userdata': b64e("NEW_USERDATA")})

        populate_dir(self.waagent_d,
            {'ovf-env.xml': cached_ovfenv,
             'SharedConfig.xml': "mysharedconfigxml",
             'otherfile': 'otherfilecontent'})

        dsrc = self._get_ds({'ovfcontent': new_ovfenv})
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, b"NEW_USERDATA")
        self.assertTrue(os.path.exists(
            os.path.join(self.waagent_d, 'otherfile')))
        self.assertFalse(
            os.path.exists(os.path.join(self.waagent_d, 'SharedConfig.xml')))
        self.assertTrue(
            os.path.exists(os.path.join(self.waagent_d, 'ovf-env.xml')))
        self.assertEqual(new_ovfenv,
            load_file(os.path.join(self.waagent_d, 'ovf-env.xml')))


class TestAzureBounce(TestCase):

    def mock_out_azure_moving_parts(self):
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'invoke_agent'))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'wait_for_files'))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'iid_from_shared_config',
                              mock.MagicMock(return_value='i-my-azure-id')))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'list_possible_azure_ds_devs',
                              mock.MagicMock(return_value=[])))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'find_ephemeral_disk',
                              mock.MagicMock(return_value=None)))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'find_ephemeral_part',
                              mock.MagicMock(return_value=None)))

    def setUp(self):
        super(TestAzureBounce, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.waagent_d = os.path.join(self.tmp, 'var', 'lib', 'waagent')
        self.paths = helpers.Paths({'cloud_dir': self.tmp})
        self.addCleanup(shutil.rmtree, self.tmp)
        DataSourceAzure.BUILTIN_DS_CONFIG['data_dir'] = self.waagent_d
        self.patches = ExitStack()
        self.mock_out_azure_moving_parts()
        self.get_hostname = self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'get_hostname'))
        self.set_hostname = self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'set_hostname'))
        self.subp = self.patches.enter_context(
            mock.patch('cloudinit.sources.DataSourceAzure.util.subp'))

    def tearDown(self):
        self.patches.close()

    def _get_ds(self, ovfcontent=None):
        if ovfcontent is not None:
            populate_dir(os.path.join(self.paths.seed_dir, "azure"),
                         {'ovf-env.xml': ovfcontent})
        return DataSourceAzure.DataSourceAzureNet(
            {}, distro=None, paths=self.paths)

    def get_ovf_env_with_dscfg(self, hostname, cfg):
        odata = {
            'HostName': hostname,
            'dscfg': {
                'text': b64e(yaml.dump(cfg)),
                'encoding': 'base64'
            }
        }
        return construct_valid_ovf_env(data=odata)

    def test_disabled_bounce_does_not_change_hostname(self):
        cfg = {'hostname_bounce': {'policy': 'off'}}
        self._get_ds(self.get_ovf_env_with_dscfg('test-host', cfg)).get_data()
        self.assertEqual(0, self.set_hostname.call_count)

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_disabled_bounce_does_not_perform_bounce(
            self, perform_hostname_bounce):
        cfg = {'hostname_bounce': {'policy': 'off'}}
        self._get_ds(self.get_ovf_env_with_dscfg('test-host', cfg)).get_data()
        self.assertEqual(0, perform_hostname_bounce.call_count)

    def test_same_hostname_does_not_change_hostname(self):
        host_name = 'unchanged-host-name'
        self.get_hostname.return_value = host_name
        cfg = {'hostname_bounce': {'policy': 'yes'}}
        self._get_ds(self.get_ovf_env_with_dscfg(host_name, cfg)).get_data()
        self.assertEqual(0, self.set_hostname.call_count)

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_unchanged_hostname_does_not_perform_bounce(
            self, perform_hostname_bounce):
        host_name = 'unchanged-host-name'
        self.get_hostname.return_value = host_name
        cfg = {'hostname_bounce': {'policy': 'yes'}}
        self._get_ds(self.get_ovf_env_with_dscfg(host_name, cfg)).get_data()
        self.assertEqual(0, perform_hostname_bounce.call_count)

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_force_performs_bounce_regardless(self, perform_hostname_bounce):
        host_name = 'unchanged-host-name'
        self.get_hostname.return_value = host_name
        cfg = {'hostname_bounce': {'policy': 'force'}}
        self._get_ds(self.get_ovf_env_with_dscfg(host_name, cfg)).get_data()
        self.assertEqual(1, perform_hostname_bounce.call_count)

    def test_different_hostnames_sets_hostname(self):
        expected_hostname = 'azure-expected-host-name'
        self.get_hostname.return_value = 'default-host-name'
        self._get_ds(
            self.get_ovf_env_with_dscfg(expected_hostname, {})).get_data()
        self.assertEqual(expected_hostname,
                         self.set_hostname.call_args_list[0][0][0])

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_different_hostnames_performs_bounce(
            self, perform_hostname_bounce):
        expected_hostname = 'azure-expected-host-name'
        self.get_hostname.return_value = 'default-host-name'
        self._get_ds(
            self.get_ovf_env_with_dscfg(expected_hostname, {})).get_data()
        self.assertEqual(1, perform_hostname_bounce.call_count)

    def test_different_hostnames_sets_hostname_back(self):
        initial_host_name = 'default-host-name'
        self.get_hostname.return_value = initial_host_name
        self._get_ds(
            self.get_ovf_env_with_dscfg('some-host-name', {})).get_data()
        self.assertEqual(initial_host_name,
                         self.set_hostname.call_args_list[-1][0][0])

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_failure_in_bounce_still_resets_host_name(
            self, perform_hostname_bounce):
        perform_hostname_bounce.side_effect = Exception
        initial_host_name = 'default-host-name'
        self.get_hostname.return_value = initial_host_name
        self._get_ds(
            self.get_ovf_env_with_dscfg('some-host-name', {})).get_data()
        self.assertEqual(initial_host_name,
                         self.set_hostname.call_args_list[-1][0][0])

    def test_environment_correct_for_bounce_command(self):
        interface = 'int0'
        hostname = 'my-new-host'
        old_hostname = 'my-old-host'
        self.get_hostname.return_value = old_hostname
        cfg = {'hostname_bounce': {'interface': interface, 'policy': 'force'}}
        data = self.get_ovf_env_with_dscfg(hostname, cfg)
        self._get_ds(data).get_data()
        self.assertEqual(1, self.subp.call_count)
        bounce_env = self.subp.call_args[1]['env']
        self.assertEqual(interface, bounce_env['interface'])
        self.assertEqual(hostname, bounce_env['hostname'])
        self.assertEqual(old_hostname, bounce_env['old_hostname'])

    def test_default_bounce_command_used_by_default(self):
        cmd = 'default-bounce-command'
        DataSourceAzure.BUILTIN_DS_CONFIG['hostname_bounce']['command'] = cmd
        cfg = {'hostname_bounce': {'policy': 'force'}}
        data = self.get_ovf_env_with_dscfg('some-hostname', cfg)
        self._get_ds(data).get_data()
        self.assertEqual(1, self.subp.call_count)
        bounce_args = self.subp.call_args[1]['args']
        self.assertEqual(cmd, bounce_args)

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_set_hostname_option_can_disable_bounce(
            self, perform_hostname_bounce):
        cfg = {'set_hostname': False, 'hostname_bounce': {'policy': 'force'}}
        data = self.get_ovf_env_with_dscfg('some-hostname', cfg)
        self._get_ds(data).get_data()

        self.assertEqual(0, perform_hostname_bounce.call_count)

    def test_set_hostname_option_can_disable_hostname_set(self):
        cfg = {'set_hostname': False, 'hostname_bounce': {'policy': 'force'}}
        data = self.get_ovf_env_with_dscfg('some-hostname', cfg)
        self._get_ds(data).get_data()

        self.assertEqual(0, self.set_hostname.call_count)


class TestReadAzureOvf(TestCase):
    def test_invalid_xml_raises_non_azure_ds(self):
        invalid_xml = "<foo>" + construct_valid_ovf_env(data={})
        self.assertRaises(DataSourceAzure.BrokenAzureDataSource,
            DataSourceAzure.read_azure_ovf, invalid_xml)

    def test_load_with_pubkeys(self):
        mypklist = [{'fingerprint': 'fp1', 'path': 'path1'}]
        pubkeys = [(x['fingerprint'], x['path']) for x in mypklist]
        content = construct_valid_ovf_env(pubkeys=pubkeys)
        (_md, _ud, cfg) = DataSourceAzure.read_azure_ovf(content)
        for mypk in mypklist:
            self.assertIn(mypk, cfg['_pubkeys'])


class TestReadAzureSharedConfig(unittest.TestCase):
    def test_valid_content(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
            <SharedConfig>
             <Deployment name="MY_INSTANCE_ID">
              <Service name="myservice"/>
              <ServiceInstance name="INSTANCE_ID.0" guid="{abcd-uuid}" />
             </Deployment>
            <Incarnation number="1"/>
            </SharedConfig>"""
        ret = DataSourceAzure.iid_from_shared_config_content(xml)
        self.assertEqual("MY_INSTANCE_ID", ret)


class TestFindEndpoint(TestCase):

    def setUp(self):
        super(TestFindEndpoint, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.load_file = patches.enter_context(
            mock.patch.object(DataSourceAzure.util, 'load_file'))

    def test_missing_file(self):
        self.load_file.side_effect = IOError
        self.assertRaises(IOError, DataSourceAzure.find_endpoint)

    def test_missing_special_azure_line(self):
        self.load_file.return_value = ''
        self.assertRaises(Exception, DataSourceAzure.find_endpoint)

    def _build_lease_content(self, ip_address, use_hex=True):
        ip_address_repr = ':'.join(
            [hex(int(part)).replace('0x', '')
             for part in ip_address.split('.')])
        if not use_hex:
            ip_address_repr = struct.pack(
                '>L', int(ip_address_repr.replace(':', ''), 16))
            ip_address_repr = '"{0}"'.format(ip_address_repr.decode('utf-8'))
        return '\n'.join([
            'lease {',
            ' interface "eth0";',
            ' option unknown-245 {0};'.format(ip_address_repr),
            '}'])

    def test_hex_string(self):
        ip_address = '98.76.54.32'
        file_content = self._build_lease_content(ip_address)
        self.load_file.return_value = file_content
        self.assertEqual(ip_address, DataSourceAzure.find_endpoint())

    def test_hex_string_with_single_character_part(self):
        ip_address = '4.3.2.1'
        file_content = self._build_lease_content(ip_address)
        self.load_file.return_value = file_content
        self.assertEqual(ip_address, DataSourceAzure.find_endpoint())

    def test_packed_string(self):
        ip_address = '98.76.54.32'
        file_content = self._build_lease_content(ip_address, use_hex=False)
        self.load_file.return_value = file_content
        self.assertEqual(ip_address, DataSourceAzure.find_endpoint())

    def test_latest_lease_used(self):
        ip_addresses = ['4.3.2.1', '98.76.54.32']
        file_content = '\n'.join([self._build_lease_content(ip_address)
                                  for ip_address in ip_addresses])
        self.load_file.return_value = file_content
        self.assertEqual(ip_addresses[-1], DataSourceAzure.find_endpoint())


class TestGoalStateParsing(TestCase):

    default_parameters = {
        'incarnation': 1,
        'container_id': 'MyContainerId',
        'instance_id': 'MyInstanceId',
        'shared_config_url': 'MySharedConfigUrl',
        'certificates_url': 'MyCertificatesUrl',
    }

    def _get_goal_state(self, http_client=None, **kwargs):
        if http_client is None:
            http_client = mock.MagicMock()
        parameters = self.default_parameters.copy()
        parameters.update(kwargs)
        xml = GOAL_STATE_TEMPLATE.format(**parameters)
        if parameters['certificates_url'] is None:
            new_xml_lines = []
            for line in xml.splitlines():
                if 'Certificates' in line:
                    continue
                new_xml_lines.append(line)
            xml = '\n'.join(new_xml_lines)
        return DataSourceAzure.GoalState(xml, http_client)

    def test_incarnation_parsed_correctly(self):
        incarnation = '123'
        goal_state = self._get_goal_state(incarnation=incarnation)
        self.assertEqual(incarnation, goal_state.incarnation)

    def test_container_id_parsed_correctly(self):
        container_id = 'TestContainerId'
        goal_state = self._get_goal_state(container_id=container_id)
        self.assertEqual(container_id, goal_state.container_id)

    def test_instance_id_parsed_correctly(self):
        instance_id = 'TestInstanceId'
        goal_state = self._get_goal_state(instance_id=instance_id)
        self.assertEqual(instance_id, goal_state.instance_id)

    def test_shared_config_xml_parsed_and_fetched_correctly(self):
        http_client = mock.MagicMock()
        shared_config_url = 'TestSharedConfigUrl'
        goal_state = self._get_goal_state(
            http_client=http_client, shared_config_url=shared_config_url)
        shared_config_xml = goal_state.shared_config_xml
        self.assertEqual(1, http_client.get.call_count)
        self.assertEqual(shared_config_url, http_client.get.call_args[0][0])
        self.assertEqual(http_client.get.return_value.contents,
                         shared_config_xml)

    def test_certificates_xml_parsed_and_fetched_correctly(self):
        http_client = mock.MagicMock()
        certificates_url = 'TestSharedConfigUrl'
        goal_state = self._get_goal_state(
            http_client=http_client, certificates_url=certificates_url)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(1, http_client.get.call_count)
        self.assertEqual(certificates_url, http_client.get.call_args[0][0])
        self.assertTrue(http_client.get.call_args[1].get('secure', False))
        self.assertEqual(http_client.get.return_value.contents,
                         certificates_xml)

    def test_missing_certificates_skips_http_get(self):
        http_client = mock.MagicMock()
        goal_state = self._get_goal_state(
            http_client=http_client, certificates_url=None)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(0, http_client.get.call_count)
        self.assertIsNone(certificates_xml)


class TestAzureEndpointHttpClient(TestCase):

    regular_headers = {
        'x-ms-agent-name': 'WALinuxAgent',
        'x-ms-version': '2012-11-30',
    }

    def setUp(self):
        super(TestAzureEndpointHttpClient, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.read_file_or_url = patches.enter_context(
            mock.patch.object(DataSourceAzure.util, 'read_file_or_url'))

    def test_non_secure_get(self):
        client = DataSourceAzure.AzureEndpointHttpClient(mock.MagicMock())
        url = 'MyTestUrl'
        response = client.get(url, secure=False)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(mock.call(url, headers=self.regular_headers),
                         self.read_file_or_url.call_args)

    def test_secure_get(self):
        url = 'MyTestUrl'
        certificate = mock.MagicMock()
        expected_headers = self.regular_headers.copy()
        expected_headers.update({
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": certificate,
        })
        client = DataSourceAzure.AzureEndpointHttpClient(certificate)
        response = client.get(url, secure=True)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(mock.call(url, headers=expected_headers),
                         self.read_file_or_url.call_args)

    def test_post(self):
        data = mock.MagicMock()
        url = 'MyTestUrl'
        client = DataSourceAzure.AzureEndpointHttpClient(mock.MagicMock())
        response = client.post(url, data=data)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(
            mock.call(url, data=data, headers=self.regular_headers),
            self.read_file_or_url.call_args)

    def test_post_with_extra_headers(self):
        url = 'MyTestUrl'
        client = DataSourceAzure.AzureEndpointHttpClient(mock.MagicMock())
        extra_headers = {'test': 'header'}
        client.post(url, extra_headers=extra_headers)
        self.assertEqual(1, self.read_file_or_url.call_count)
        expected_headers = self.regular_headers.copy()
        expected_headers.update(extra_headers)
        self.assertEqual(
            mock.call(mock.ANY, data=mock.ANY, headers=expected_headers),
            self.read_file_or_url.call_args)


class TestOpenSSLManager(TestCase):

    def setUp(self):
        super(TestOpenSSLManager, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.subp = patches.enter_context(
            mock.patch.object(DataSourceAzure.util, 'subp'))

    @mock.patch.object(DataSourceAzure, 'cd', mock.MagicMock())
    @mock.patch.object(DataSourceAzure.tempfile, 'TemporaryDirectory')
    def test_openssl_manager_creates_a_tmpdir(self, TemporaryDirectory):
        manager = DataSourceAzure.OpenSSLManager()
        self.assertEqual(TemporaryDirectory.return_value, manager.tmpdir)

    @mock.patch('builtins.open')
    def test_generate_certificate_uses_tmpdir(self, open):
        subp_directory = {}

        def capture_directory(*args, **kwargs):
            subp_directory['path'] = os.getcwd()

        self.subp.side_effect = capture_directory
        manager = DataSourceAzure.OpenSSLManager()
        self.assertEqual(manager.tmpdir.name, subp_directory['path'])


class TestWALinuxAgentShim(TestCase):

    def setUp(self):
        super(TestWALinuxAgentShim, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.AzureEndpointHttpClient = patches.enter_context(
            mock.patch.object(DataSourceAzure, 'AzureEndpointHttpClient'))
        self.find_endpoint = patches.enter_context(
            mock.patch.object(DataSourceAzure, 'find_endpoint'))
        self.GoalState = patches.enter_context(
            mock.patch.object(DataSourceAzure, 'GoalState'))
        self.iid_from_shared_config_content = patches.enter_context(
            mock.patch.object(DataSourceAzure,
                              'iid_from_shared_config_content'))
        self.OpenSSLManager = patches.enter_context(
            mock.patch.object(DataSourceAzure, 'OpenSSLManager'))

    def test_http_client_uses_certificate(self):
        shim = DataSourceAzure.WALinuxAgentShim()
        self.assertEqual(
            [mock.call(self.OpenSSLManager.return_value.certificate)],
            self.AzureEndpointHttpClient.call_args_list)
        self.assertEqual(self.AzureEndpointHttpClient.return_value,
                         shim.http_client)

    def test_correct_url_used_for_goalstate(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = DataSourceAzure.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        get = self.AzureEndpointHttpClient.return_value.get
        self.assertEqual(
            [mock.call('http://test_endpoint/machine/?comp=goalstate')],
            get.call_args_list)
        self.assertEqual(
            [mock.call(get.return_value.contents, shim.http_client)],
            self.GoalState.call_args_list)

    def test_certificates_used_to_determine_public_keys(self):
        shim = DataSourceAzure.WALinuxAgentShim()
        data = shim.register_with_azure_and_fetch_data()
        self.assertEqual(
            [mock.call(self.GoalState.return_value.certificates_xml)],
            self.OpenSSLManager.return_value.parse_certificates.call_args_list)
        self.assertEqual(
            self.OpenSSLManager.return_value.parse_certificates.return_value,
            data['public-keys'])

    def test_absent_certificates_produces_empty_public_keys(self):
        self.GoalState.return_value.certificates_xml = None
        shim = DataSourceAzure.WALinuxAgentShim()
        data = shim.register_with_azure_and_fetch_data()
        self.assertEqual([], data['public-keys'])

    def test_instance_id_returned_in_data(self):
        shim = DataSourceAzure.WALinuxAgentShim()
        data = shim.register_with_azure_and_fetch_data()
        self.assertEqual(
            [mock.call(self.GoalState.return_value.shared_config_xml)],
            self.iid_from_shared_config_content.call_args_list)
        self.assertEqual(self.iid_from_shared_config_content.return_value,
                         data['instance-id'])

    def test_correct_url_used_for_report_ready(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = DataSourceAzure.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        expected_url = 'http://test_endpoint/machine?comp=health'
        self.assertEqual(
            [mock.call(expected_url, data=mock.ANY, extra_headers=mock.ANY)],
            shim.http_client.post.call_args_list)

    def test_goal_state_values_used_for_report_ready(self):
        self.GoalState.return_value.incarnation = 'TestIncarnation'
        self.GoalState.return_value.container_id = 'TestContainerId'
        self.GoalState.return_value.instance_id = 'TestInstanceId'
        shim = DataSourceAzure.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        posted_document = shim.http_client.post.call_args[1]['data']
        self.assertIn('TestIncarnation', posted_document)
        self.assertIn('TestContainerId', posted_document)
        self.assertIn('TestInstanceId', posted_document)
