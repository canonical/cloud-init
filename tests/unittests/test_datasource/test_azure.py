# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit.util import b64e, decode_binary, load_file
from cloudinit.sources import DataSourceAzure

from ..helpers import TestCase, populate_dir, mock, ExitStack, PY26, SkipTest

import crypt
import os
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
import yaml


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
        for fp, path, value in pubkeys:
            content += " <PublicKey>"
            if fp and path:
                content += ("<Fingerprint>%s</Fingerprint><Path>%s</Path>" %
                            (fp, path))
            if value:
                content += "<Value>%s</Value>" % value
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
        if PY26:
            raise SkipTest("Does not work on python 2.6")
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

    def _get_ds(self, data, agent_command=None):

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

        if data.get('ovfcontent') is not None:
            populate_dir(os.path.join(self.paths.seed_dir, "azure"),
                         {'ovf-env.xml': data['ovfcontent']})

        mod = DataSourceAzure
        mod.BUILTIN_DS_CONFIG['data_dir'] = self.waagent_d

        self.get_metadata_from_fabric = mock.MagicMock(return_value={
            'public-keys': [],
        })

        self.instance_id = 'test-instance-id'

        self.apply_patches([
            (mod, 'list_possible_azure_ds_devs', dsdevs),
            (mod, 'invoke_agent', _invoke_agent),
            (mod, 'wait_for_files', _wait_for_files),
            (mod, 'pubkeys_from_crt_files', _pubkeys_from_crt_files),
            (mod, 'perform_hostname_bounce', mock.MagicMock()),
            (mod, 'get_hostname', mock.MagicMock()),
            (mod, 'set_hostname', mock.MagicMock()),
            (mod, 'get_metadata_from_fabric', self.get_metadata_from_fabric),
            (mod.util, 'read_dmi_data', mock.MagicMock(
                return_value=self.instance_id)),
        ])

        dsrc = mod.DataSourceAzureNet(
            data.get('sys_cfg', {}), distro=None, paths=self.paths)
        if agent_command is not None:
            dsrc.ds_cfg['agent_command'] = agent_command

        return dsrc

    def xml_equals(self, oxml, nxml):
        """Compare two sets of XML to make sure they are equal"""

        def create_tag_index(xml):
            et = ET.fromstring(xml)
            ret = {}
            for x in et.iter():
                ret[x.tag] = x
            return ret

        def tags_exists(x, y):
            for tag in x.keys():
                self.assertIn(tag, y)
            for tag in y.keys():
                self.assertIn(tag, x)

        def tags_equal(x, y):
            for x_tag, x_val in x.items():
                y_val = y.get(x_val.tag)
                self.assertEqual(x_val.text, y_val.text)

        old_cnt = create_tag_index(oxml)
        new_cnt = create_tag_index(nxml)
        tags_exists(old_cnt, new_cnt)
        tags_equal(old_cnt, new_cnt)

    def xml_notequals(self, oxml, nxml):
        try:
            self.xml_equals(oxml, nxml)
        except AssertionError:
            return
        raise AssertionError("XML is the same")

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
                         crypt.crypt(odata['UserPassword'],
                                     defuser['passwd'][0:pos]))

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

    def test_cfg_has_pubkeys_fingerprint(self):
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        mypklist = [{'fingerprint': 'fp1', 'path': 'path1', 'value': ''}]
        pubkeys = [(x['fingerprint'], x['path'], x['value']) for x in mypklist]
        data = {'ovfcontent': construct_valid_ovf_env(data=odata,
                                                      pubkeys=pubkeys)}

        dsrc = self._get_ds(data, agent_command=['not', '__builtin__'])
        ret = dsrc.get_data()
        self.assertTrue(ret)
        for mypk in mypklist:
            self.assertIn(mypk, dsrc.cfg['_pubkeys'])
            self.assertIn('pubkey_from', dsrc.metadata['public-keys'][-1])

    def test_cfg_has_pubkeys_value(self):
        # make sure that provided key is used over fingerprint
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        mypklist = [{'fingerprint': 'fp1', 'path': 'path1', 'value': 'value1'}]
        pubkeys = [(x['fingerprint'], x['path'], x['value']) for x in mypklist]
        data = {'ovfcontent': construct_valid_ovf_env(data=odata,
                                                      pubkeys=pubkeys)}

        dsrc = self._get_ds(data, agent_command=['not', '__builtin__'])
        ret = dsrc.get_data()
        self.assertTrue(ret)

        for mypk in mypklist:
            self.assertIn(mypk, dsrc.cfg['_pubkeys'])
            self.assertIn(mypk['value'], dsrc.metadata['public-keys'])

    def test_cfg_has_no_fingerprint_has_value(self):
        # test value is used when fingerprint not provided
        odata = {'HostName': "myhost", 'UserName': "myuser"}
        mypklist = [{'fingerprint': None, 'path': 'path1', 'value': 'value1'}]
        pubkeys = [(x['fingerprint'], x['path'], x['value']) for x in mypklist]
        data = {'ovfcontent': construct_valid_ovf_env(data=odata,
                                                      pubkeys=pubkeys)}

        dsrc = self._get_ds(data, agent_command=['not', '__builtin__'])
        ret = dsrc.get_data()
        self.assertTrue(ret)

        for mypk in mypklist:
            self.assertIn(mypk['value'], dsrc.metadata['public-keys'])

    def test_default_ephemeral(self):
        # make sure the ephemeral device works
        odata = {}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata),
                'sys_cfg': {}}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        cfg = dsrc.get_config_obj()

        self.assertEqual(dsrc.device_name_to_device("ephemeral0"),
                         DataSourceAzure.RESOURCE_DISK_PATH)
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

    def test_password_redacted_in_ovf(self):
        odata = {'HostName': "myhost", 'UserName': "myuser",
                 'UserPassword': "mypass"}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}
        dsrc = self._get_ds(data)
        ret = dsrc.get_data()

        self.assertTrue(ret)
        ovf_env_path = os.path.join(self.waagent_d, 'ovf-env.xml')

        # The XML should not be same since the user password is redacted
        on_disk_ovf = load_file(ovf_env_path)
        self.xml_notequals(data['ovfcontent'], on_disk_ovf)

        # Make sure that the redacted password on disk is not used by CI
        self.assertNotEqual(dsrc.cfg.get('password'),
                            DataSourceAzure.DEF_PASSWD_REDACTION)

        # Make sure that the password was really encrypted
        et = ET.fromstring(on_disk_ovf)
        for elem in et.iter():
            if 'UserPassword' in elem.tag:
                self.assertEqual(DataSourceAzure.DEF_PASSWD_REDACTION,
                                 elem.text)

    def test_ovf_env_arrives_in_waagent_dir(self):
        xml = construct_valid_ovf_env(data={}, userdata="FOODATA")
        dsrc = self._get_ds({'ovfcontent': xml})
        dsrc.get_data()

        # 'data_dir' is '/var/lib/waagent' (walinux-agent's state dir)
        # we expect that the ovf-env.xml file is copied there.
        ovf_env_path = os.path.join(self.waagent_d, 'ovf-env.xml')
        self.assertTrue(os.path.exists(ovf_env_path))
        self.xml_equals(xml, load_file(ovf_env_path))

    def test_ovf_can_include_unicode(self):
        xml = construct_valid_ovf_env(data={})
        xml = u'\ufeff{0}'.format(xml)
        dsrc = self._get_ds({'ovfcontent': xml})
        dsrc.get_data()

    def test_exception_fetching_fabric_data_doesnt_propagate(self):
        ds = self._get_ds({'ovfcontent': construct_valid_ovf_env()})
        ds.ds_cfg['agent_command'] = '__builtin__'
        self.get_metadata_from_fabric.side_effect = Exception
        self.assertFalse(ds.get_data())

    def test_fabric_data_included_in_metadata(self):
        ds = self._get_ds({'ovfcontent': construct_valid_ovf_env()})
        ds.ds_cfg['agent_command'] = '__builtin__'
        self.get_metadata_from_fabric.return_value = {'test': 'value'}
        ret = ds.get_data()
        self.assertTrue(ret)
        self.assertEqual('value', ds.metadata['test'])

    def test_instance_id_from_dmidecode_used(self):
        ds = self._get_ds({'ovfcontent': construct_valid_ovf_env()})
        ds.get_data()
        self.assertEqual(self.instance_id, ds.metadata['instance-id'])

    def test_instance_id_from_dmidecode_used_for_builtin(self):
        ds = self._get_ds({'ovfcontent': construct_valid_ovf_env()})
        ds.ds_cfg['agent_command'] = '__builtin__'
        ds.get_data()
        self.assertEqual(self.instance_id, ds.metadata['instance-id'])


class TestAzureBounce(TestCase):

    def mock_out_azure_moving_parts(self):
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'invoke_agent'))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'wait_for_files'))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'list_possible_azure_ds_devs',
                              mock.MagicMock(return_value=[])))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure, 'get_metadata_from_fabric',
                              mock.MagicMock(return_value={})))
        self.patches.enter_context(
            mock.patch.object(DataSourceAzure.util, 'read_dmi_data',
                              mock.MagicMock(return_value='test-instance-id')))

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

    def _get_ds(self, ovfcontent=None, agent_command=None):
        if ovfcontent is not None:
            populate_dir(os.path.join(self.paths.seed_dir, "azure"),
                         {'ovf-env.xml': ovfcontent})
        dsrc = DataSourceAzure.DataSourceAzureNet(
            {}, distro=None, paths=self.paths)
        if agent_command is not None:
            dsrc.ds_cfg['agent_command'] = agent_command
        return dsrc

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
        self._get_ds(self.get_ovf_env_with_dscfg(host_name, cfg),
                     agent_command=['not', '__builtin__']).get_data()
        self.assertEqual(1, perform_hostname_bounce.call_count)

    def test_different_hostnames_sets_hostname(self):
        expected_hostname = 'azure-expected-host-name'
        self.get_hostname.return_value = 'default-host-name'
        self._get_ds(
            self.get_ovf_env_with_dscfg(expected_hostname, {}),
            agent_command=['not', '__builtin__'],
        ).get_data()
        self.assertEqual(expected_hostname,
                         self.set_hostname.call_args_list[0][0][0])

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_different_hostnames_performs_bounce(
            self, perform_hostname_bounce):
        expected_hostname = 'azure-expected-host-name'
        self.get_hostname.return_value = 'default-host-name'
        self._get_ds(
            self.get_ovf_env_with_dscfg(expected_hostname, {}),
            agent_command=['not', '__builtin__'],
        ).get_data()
        self.assertEqual(1, perform_hostname_bounce.call_count)

    def test_different_hostnames_sets_hostname_back(self):
        initial_host_name = 'default-host-name'
        self.get_hostname.return_value = initial_host_name
        self._get_ds(
            self.get_ovf_env_with_dscfg('some-host-name', {}),
            agent_command=['not', '__builtin__'],
        ).get_data()
        self.assertEqual(initial_host_name,
                         self.set_hostname.call_args_list[-1][0][0])

    @mock.patch('cloudinit.sources.DataSourceAzure.perform_hostname_bounce')
    def test_failure_in_bounce_still_resets_host_name(
            self, perform_hostname_bounce):
        perform_hostname_bounce.side_effect = Exception
        initial_host_name = 'default-host-name'
        self.get_hostname.return_value = initial_host_name
        self._get_ds(
            self.get_ovf_env_with_dscfg('some-host-name', {}),
            agent_command=['not', '__builtin__'],
        ).get_data()
        self.assertEqual(initial_host_name,
                         self.set_hostname.call_args_list[-1][0][0])

    def test_environment_correct_for_bounce_command(self):
        interface = 'int0'
        hostname = 'my-new-host'
        old_hostname = 'my-old-host'
        self.get_hostname.return_value = old_hostname
        cfg = {'hostname_bounce': {'interface': interface, 'policy': 'force'}}
        data = self.get_ovf_env_with_dscfg(hostname, cfg)
        self._get_ds(data, agent_command=['not', '__builtin__']).get_data()
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
        self._get_ds(data, agent_command=['not', '__builtin__']).get_data()
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
        mypklist = [{'fingerprint': 'fp1', 'path': 'path1', 'value': ''}]
        pubkeys = [(x['fingerprint'], x['path'], x['value']) for x in mypklist]
        content = construct_valid_ovf_env(pubkeys=pubkeys)
        (_md, _ud, cfg) = DataSourceAzure.read_azure_ovf(content)
        for mypk in mypklist:
            self.assertIn(mypk, cfg['_pubkeys'])

# vi: ts=4 expandtab
