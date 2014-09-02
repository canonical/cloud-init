from cloudinit import helpers
from cloudinit.util import load_file
from cloudinit.sources import DataSourceAzure
from ..helpers import populate_dir

import base64
import crypt
from mocker import MockerTestCase
import os
import stat
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
        content += "<UserData>%s</UserData>\n" % (base64.b64encode(userdata))

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


class TestAzureDataSource(MockerTestCase):

    def setUp(self):
        # makeDir comes from MockerTestCase
        self.tmp = self.makeDir()

        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        self.paths = helpers.Paths({'cloud_dir': self.tmp})
        self.waagent_d = os.path.join(self.tmp, 'var', 'lib', 'waagent')

        self.unapply = []
        super(TestAzureDataSource, self).setUp()

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])
        super(TestAzureDataSource, self).tearDown()

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

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

        def _apply_hostname_bounce(**kwargs):
            data['apply_hostname_bounce'] = kwargs

        if data.get('ovfcontent') is not None:
            populate_dir(os.path.join(self.paths.seed_dir, "azure"),
                         {'ovf-env.xml': data['ovfcontent']})

        mod = DataSourceAzure
        mod.BUILTIN_DS_CONFIG['data_dir'] = self.waagent_d

        self.apply_patches([(mod, 'list_possible_azure_ds_devs', dsdevs)])

        self.apply_patches([(mod, 'invoke_agent', _invoke_agent),
                            (mod, 'wait_for_files', _wait_for_files),
                            (mod, 'pubkeys_from_crt_files',
                             _pubkeys_from_crt_files),
                            (mod, 'iid_from_shared_config',
                             _iid_from_shared_config),
                            (mod, 'apply_hostname_bounce',
                             _apply_hostname_bounce), ])

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
        self.assertEqual(stat.S_IMODE(os.stat(self.waagent_d).st_mode), 0700)

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
                'dscfg': {'text': base64.b64encode(yaml.dump(cfg)),
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

    def test_userdata_found(self):
        mydata = "FOOBAR"
        odata = {'UserData': base64.b64encode(mydata)}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, mydata)

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

    def test_disabled_bounce(self):
        pass

    def test_apply_bounce_call_1(self):
        # hostname needs to get through to apply_hostname_bounce
        odata = {'HostName': 'my-random-hostname'}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}

        self._get_ds(data).get_data()
        self.assertIn('hostname', data['apply_hostname_bounce'])
        self.assertEqual(data['apply_hostname_bounce']['hostname'],
                         odata['HostName'])

    def test_apply_bounce_call_configurable(self):
        # hostname_bounce should be configurable in datasource cfg
        cfg = {'hostname_bounce': {'interface': 'eth1', 'policy': 'off',
                                   'command': 'my-bounce-command',
                                   'hostname_command': 'my-hostname-command'}}
        odata = {'HostName': "xhost",
                'dscfg': {'text': base64.b64encode(yaml.dump(cfg)),
                          'encoding': 'base64'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}
        self._get_ds(data).get_data()

        for k in cfg['hostname_bounce']:
            self.assertIn(k, data['apply_hostname_bounce'])

        for k, v in cfg['hostname_bounce'].items():
            self.assertEqual(data['apply_hostname_bounce'][k], v)

    def test_set_hostname_disabled(self):
        # config specifying set_hostname off should not bounce
        cfg = {'set_hostname': False}
        odata = {'HostName': "xhost",
                'dscfg': {'text': base64.b64encode(yaml.dump(cfg)),
                          'encoding': 'base64'}}
        data = {'ovfcontent': construct_valid_ovf_env(data=odata)}
        self._get_ds(data).get_data()

        self.assertEqual(data.get('apply_hostname_bounce', "N/A"), "N/A")

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
                'dscfg': {'text': base64.b64encode(yaml.dump(dscfg)),
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

        self.assertEqual(userdata, dsrc.userdata_raw)

    def test_ovf_env_arrives_in_waagent_dir(self):
        xml = construct_valid_ovf_env(data={}, userdata="FOODATA")
        dsrc = self._get_ds({'ovfcontent': xml})
        dsrc.get_data()

        # 'data_dir' is '/var/lib/waagent' (walinux-agent's state dir)
        # we expect that the ovf-env.xml file is copied there.
        ovf_env_path = os.path.join(self.waagent_d, 'ovf-env.xml')
        self.assertTrue(os.path.exists(ovf_env_path))
        self.assertEqual(xml, load_file(ovf_env_path))

    def test_existing_ovf_same(self):
        # waagent/SharedConfig left alone if found ovf-env.xml same as cached
        odata = {'UserData': base64.b64encode("SOMEUSERDATA")}
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
            {'userdata': base64.b64encode("FOO_USERDATA")})
        new_ovfenv = construct_valid_ovf_env(
            {'userdata': base64.b64encode("NEW_USERDATA")})

        populate_dir(self.waagent_d,
            {'ovf-env.xml': cached_ovfenv,
             'SharedConfig.xml': "mysharedconfigxml",
             'otherfile': 'otherfilecontent'})

        dsrc = self._get_ds({'ovfcontent': new_ovfenv})
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, "NEW_USERDATA")
        self.assertTrue(os.path.exists(
            os.path.join(self.waagent_d, 'otherfile')))
        self.assertFalse(
            os.path.exists(os.path.join(self.waagent_d, 'SharedConfig.xml')))
        self.assertTrue(
            os.path.exists(os.path.join(self.waagent_d, 'ovf-env.xml')))
        self.assertEqual(new_ovfenv,
            load_file(os.path.join(self.waagent_d, 'ovf-env.xml')))


class TestReadAzureOvf(MockerTestCase):
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


class TestReadAzureSharedConfig(MockerTestCase):
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


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret
