# This file is part of cloud-init. See LICENSE file for license information.

import copy
import inspect
import os
import six
import stat

from cloudinit.event import EventType
from cloudinit.helpers import Paths
from cloudinit import importer
from cloudinit.sources import (
    EXPERIMENTAL_TEXT, INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE,
    METADATA_UNKNOWN, REDACT_SENSITIVE_VALUE, UNSET, DataSource,
    canonical_cloud_id, redact_sensitive_keys)
from cloudinit.tests.helpers import CiTestCase, skipIf, mock
from cloudinit.user_data import UserDataProcessor
from cloudinit import util


class DataSourceTestSubclassNet(DataSource):

    dsname = 'MyTestSubclass'
    url_max_wait = 55

    def __init__(self, sys_cfg, distro, paths, custom_metadata=None,
                 custom_userdata=None, get_data_retval=True):
        super(DataSourceTestSubclassNet, self).__init__(
            sys_cfg, distro, paths)
        self._custom_userdata = custom_userdata
        self._custom_metadata = custom_metadata
        self._get_data_retval = get_data_retval

    def _get_cloud_name(self):
        return 'SubclassCloudName'

    def _get_data(self):
        if self._custom_metadata:
            self.metadata = self._custom_metadata
        else:
            self.metadata = {'availability_zone': 'myaz',
                             'local-hostname': 'test-subclass-hostname',
                             'region': 'myregion'}
        if self._custom_userdata:
            self.userdata_raw = self._custom_userdata
        else:
            self.userdata_raw = 'userdata_raw'
        self.vendordata_raw = 'vendordata_raw'
        return self._get_data_retval


class InvalidDataSourceTestSubclassNet(DataSource):
    pass


class TestDataSource(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestDataSource, self).setUp()
        self.sys_cfg = {'datasource': {'_undef': {'key1': False}}}
        self.distro = 'distrotest'  # generally should be a Distro object
        self.paths = Paths({})
        self.datasource = DataSource(self.sys_cfg, self.distro, self.paths)

    def test_datasource_init(self):
        """DataSource initializes metadata attributes, ds_cfg and ud_proc."""
        self.assertEqual(self.paths, self.datasource.paths)
        self.assertEqual(self.sys_cfg, self.datasource.sys_cfg)
        self.assertEqual(self.distro, self.datasource.distro)
        self.assertIsNone(self.datasource.userdata)
        self.assertEqual({}, self.datasource.metadata)
        self.assertIsNone(self.datasource.userdata_raw)
        self.assertIsNone(self.datasource.vendordata)
        self.assertIsNone(self.datasource.vendordata_raw)
        self.assertEqual({'key1': False}, self.datasource.ds_cfg)
        self.assertIsInstance(self.datasource.ud_proc, UserDataProcessor)

    def test_datasource_init_gets_ds_cfg_using_dsname(self):
        """Init uses DataSource.dsname for sourcing ds_cfg."""
        sys_cfg = {'datasource': {'MyTestSubclass': {'key2': False}}}
        distro = 'distrotest'  # generally should be a Distro object
        datasource = DataSourceTestSubclassNet(sys_cfg, distro, self.paths)
        self.assertEqual({'key2': False}, datasource.ds_cfg)

    def test_str_is_classname(self):
        """The string representation of the datasource is the classname."""
        self.assertEqual('DataSource', str(self.datasource))
        self.assertEqual(
            'DataSourceTestSubclassNet',
            str(DataSourceTestSubclassNet('', '', self.paths)))

    def test_datasource_get_url_params_defaults(self):
        """get_url_params default url config settings for the datasource."""
        params = self.datasource.get_url_params()
        self.assertEqual(params.max_wait_seconds, self.datasource.url_max_wait)
        self.assertEqual(params.timeout_seconds, self.datasource.url_timeout)
        self.assertEqual(params.num_retries, self.datasource.url_retries)

    def test_datasource_get_url_params_subclassed(self):
        """Subclasses can override get_url_params defaults."""
        sys_cfg = {'datasource': {'MyTestSubclass': {'key2': False}}}
        distro = 'distrotest'  # generally should be a Distro object
        datasource = DataSourceTestSubclassNet(sys_cfg, distro, self.paths)
        expected = (datasource.url_max_wait, datasource.url_timeout,
                    datasource.url_retries)
        url_params = datasource.get_url_params()
        self.assertNotEqual(self.datasource.get_url_params(), url_params)
        self.assertEqual(expected, url_params)

    def test_datasource_get_url_params_ds_config_override(self):
        """Datasource configuration options can override url param defaults."""
        sys_cfg = {
            'datasource': {
                'MyTestSubclass': {
                    'max_wait': '1', 'timeout': '2', 'retries': '3'}}}
        datasource = DataSourceTestSubclassNet(
            sys_cfg, self.distro, self.paths)
        expected = (1, 2, 3)
        url_params = datasource.get_url_params()
        self.assertNotEqual(
            (datasource.url_max_wait, datasource.url_timeout,
             datasource.url_retries),
            url_params)
        self.assertEqual(expected, url_params)

    def test_datasource_get_url_params_is_zero_or_greater(self):
        """get_url_params ignores timeouts with a value below 0."""
        # Set an override that is below 0 which gets ignored.
        sys_cfg = {'datasource': {'_undef': {'timeout': '-1'}}}
        datasource = DataSource(sys_cfg, self.distro, self.paths)
        (_max_wait, timeout, _retries) = datasource.get_url_params()
        self.assertEqual(0, timeout)

    def test_datasource_get_url_uses_defaults_on_errors(self):
        """On invalid system config values for url_params defaults are used."""
        # All invalid values should be logged
        sys_cfg = {'datasource': {
            '_undef': {
                'max_wait': 'nope', 'timeout': 'bug', 'retries': 'nonint'}}}
        datasource = DataSource(sys_cfg, self.distro, self.paths)
        url_params = datasource.get_url_params()
        expected = (datasource.url_max_wait, datasource.url_timeout,
                    datasource.url_retries)
        self.assertEqual(expected, url_params)
        logs = self.logs.getvalue()
        expected_logs = [
            "Config max_wait 'nope' is not an int, using default '-1'",
            "Config timeout 'bug' is not an int, using default '10'",
            "Config retries 'nonint' is not an int, using default '5'",
        ]
        for log in expected_logs:
            self.assertIn(log, logs)

    @mock.patch('cloudinit.sources.net.find_fallback_nic')
    def test_fallback_interface_is_discovered(self, m_get_fallback_nic):
        """The fallback_interface is discovered via find_fallback_nic."""
        m_get_fallback_nic.return_value = 'nic9'
        self.assertEqual('nic9', self.datasource.fallback_interface)

    @mock.patch('cloudinit.sources.net.find_fallback_nic')
    def test_fallback_interface_logs_undiscovered(self, m_get_fallback_nic):
        """Log a warning when fallback_interface can not discover the nic."""
        self.datasource._cloud_name = 'MySupahCloud'
        m_get_fallback_nic.return_value = None  # Couldn't discover nic
        self.assertIsNone(self.datasource.fallback_interface)
        self.assertEqual(
            'WARNING: Did not find a fallback interface on MySupahCloud.\n',
            self.logs.getvalue())

    @mock.patch('cloudinit.sources.net.find_fallback_nic')
    def test_wb_fallback_interface_is_cached(self, m_get_fallback_nic):
        """The fallback_interface is cached and won't be rediscovered."""
        self.datasource._fallback_interface = 'nic10'
        self.assertEqual('nic10', self.datasource.fallback_interface)
        m_get_fallback_nic.assert_not_called()

    def test__get_data_unimplemented(self):
        """Raise an error when _get_data is not implemented."""
        with self.assertRaises(NotImplementedError) as context_manager:
            self.datasource.get_data()
        self.assertIn(
            'Subclasses of DataSource must implement _get_data',
            str(context_manager.exception))
        datasource2 = InvalidDataSourceTestSubclassNet(
            self.sys_cfg, self.distro, self.paths)
        with self.assertRaises(NotImplementedError) as context_manager:
            datasource2.get_data()
        self.assertIn(
            'Subclasses of DataSource must implement _get_data',
            str(context_manager.exception))

    def test_get_data_calls_subclass__get_data(self):
        """Datasource.get_data uses the subclass' version of _get_data."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertTrue(datasource.get_data())
        self.assertEqual(
            {'availability_zone': 'myaz',
             'local-hostname': 'test-subclass-hostname',
             'region': 'myregion'},
            datasource.metadata)
        self.assertEqual('userdata_raw', datasource.userdata_raw)
        self.assertEqual('vendordata_raw', datasource.vendordata_raw)

    def test_get_hostname_strips_local_hostname_without_domain(self):
        """Datasource.get_hostname strips metadata local-hostname of domain."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertTrue(datasource.get_data())
        self.assertEqual(
            'test-subclass-hostname', datasource.metadata['local-hostname'])
        self.assertEqual('test-subclass-hostname', datasource.get_hostname())
        datasource.metadata['local-hostname'] = 'hostname.my.domain.com'
        self.assertEqual('hostname', datasource.get_hostname())

    def test_get_hostname_with_fqdn_returns_local_hostname_with_domain(self):
        """Datasource.get_hostname with fqdn set gets qualified hostname."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertTrue(datasource.get_data())
        datasource.metadata['local-hostname'] = 'hostname.my.domain.com'
        self.assertEqual(
            'hostname.my.domain.com', datasource.get_hostname(fqdn=True))

    def test_get_hostname_without_metadata_uses_system_hostname(self):
        """Datasource.gethostname runs util.get_hostname when no metadata."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = 'cloudinit.sources.util.get_fqdn_from_hosts'
        with mock.patch('cloudinit.sources.util.get_hostname') as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                m_gethost.return_value = 'systemhostname.domain.com'
                m_fqdn.return_value = None  # No maching fqdn in /etc/hosts
                self.assertEqual('systemhostname', datasource.get_hostname())
                self.assertEqual(
                    'systemhostname.domain.com',
                    datasource.get_hostname(fqdn=True))

    def test_get_hostname_without_metadata_returns_none(self):
        """Datasource.gethostname returns None when metadata_only and no MD."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = 'cloudinit.sources.util.get_fqdn_from_hosts'
        with mock.patch('cloudinit.sources.util.get_hostname') as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                self.assertIsNone(datasource.get_hostname(metadata_only=True))
                self.assertIsNone(
                    datasource.get_hostname(fqdn=True, metadata_only=True))
        self.assertEqual([], m_gethost.call_args_list)
        self.assertEqual([], m_fqdn.call_args_list)

    def test_get_hostname_without_metadata_prefers_etc_hosts(self):
        """Datasource.gethostname prefers /etc/hosts to util.get_hostname."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = 'cloudinit.sources.util.get_fqdn_from_hosts'
        with mock.patch('cloudinit.sources.util.get_hostname') as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                m_gethost.return_value = 'systemhostname.domain.com'
                m_fqdn.return_value = 'fqdnhostname.domain.com'
                self.assertEqual('fqdnhostname', datasource.get_hostname())
                self.assertEqual('fqdnhostname.domain.com',
                                 datasource.get_hostname(fqdn=True))

    def test_get_data_does_not_write_instance_data_on_failure(self):
        """get_data does not write INSTANCE_JSON_FILE on get_data False."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            get_data_retval=False)
        self.assertFalse(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        self.assertFalse(
            os.path.exists(json_file), 'Found unexpected file %s' % json_file)

    def test_get_data_writes_json_instance_data_on_success(self):
        """get_data writes INSTANCE_JSON_FILE to run_dir as world readable."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        expected = {
            'base64_encoded_keys': [],
            'sensitive_keys': [],
            'v1': {
                '_beta_keys': ['subplatform'],
                'availability-zone': 'myaz',
                'availability_zone': 'myaz',
                'cloud-name': 'subclasscloudname',
                'cloud_name': 'subclasscloudname',
                'instance-id': 'iid-datasource',
                'instance_id': 'iid-datasource',
                'local-hostname': 'test-subclass-hostname',
                'local_hostname': 'test-subclass-hostname',
                'platform': 'mytestsubclass',
                'public_ssh_keys': [],
                'region': 'myregion',
                'subplatform': 'unknown'},
            'ds': {
                '_doc': EXPERIMENTAL_TEXT,
                'meta_data': {'availability_zone': 'myaz',
                              'local-hostname': 'test-subclass-hostname',
                              'region': 'myregion'}}}
        self.assertEqual(expected, util.load_json(content))
        file_stat = os.stat(json_file)
        self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))
        self.assertEqual(expected, util.load_json(content))

    def test_get_data_writes_json_instance_data_sensitive(self):
        """get_data writes INSTANCE_JSON_SENSITIVE_FILE as readonly root."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_metadata={
                'availability_zone': 'myaz',
                'local-hostname': 'test-subclass-hostname',
                'region': 'myregion',
                'some': {'security-credentials': {
                    'cred1': 'sekret', 'cred2': 'othersekret'}}})
        self.assertEqual(
            ('security-credentials',), datasource.sensitive_metadata_keys)
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        sensitive_json_file = self.tmp_path(INSTANCE_JSON_SENSITIVE_FILE, tmp)
        redacted = util.load_json(util.load_file(json_file))
        self.assertEqual(
            {'cred1': 'sekret', 'cred2': 'othersekret'},
            redacted['ds']['meta_data']['some']['security-credentials'])
        content = util.load_file(sensitive_json_file)
        expected = {
            'base64_encoded_keys': [],
            'sensitive_keys': ['ds/meta_data/some/security-credentials'],
            'v1': {
                '_beta_keys': ['subplatform'],
                'availability-zone': 'myaz',
                'availability_zone': 'myaz',
                'cloud-name': 'subclasscloudname',
                'cloud_name': 'subclasscloudname',
                'instance-id': 'iid-datasource',
                'instance_id': 'iid-datasource',
                'local-hostname': 'test-subclass-hostname',
                'local_hostname': 'test-subclass-hostname',
                'platform': 'mytestsubclass',
                'public_ssh_keys': [],
                'region': 'myregion',
                'subplatform': 'unknown'},
            'ds': {
                '_doc': EXPERIMENTAL_TEXT,
                'meta_data': {
                    'availability_zone': 'myaz',
                    'local-hostname': 'test-subclass-hostname',
                    'region': 'myregion',
                    'some': {'security-credentials': REDACT_SENSITIVE_VALUE}}}
        }
        self.maxDiff = None
        self.assertEqual(expected, util.load_json(content))
        file_stat = os.stat(sensitive_json_file)
        self.assertEqual(0o600, stat.S_IMODE(file_stat.st_mode))
        self.assertEqual(expected, util.load_json(content))

    def test_get_data_handles_redacted_unserializable_content(self):
        """get_data warns unserializable content in INSTANCE_JSON_FILE."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_metadata={'key1': 'val1', 'key2': {'key2.1': self.paths}})
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        expected_metadata = {
            'key1': 'val1',
            'key2': {
                'key2.1': "Warning: redacted unserializable type <class"
                          " 'cloudinit.helpers.Paths'>"}}
        instance_json = util.load_json(content)
        self.assertEqual(
            expected_metadata, instance_json['ds']['meta_data'])

    def test_persist_instance_data_writes_ec2_metadata_when_set(self):
        """When ec2_metadata class attribute is set, persist to json."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        datasource.ec2_metadata = UNSET
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        instance_data = util.load_json(util.load_file(json_file))
        self.assertNotIn('ec2_metadata', instance_data['ds'])
        datasource.ec2_metadata = {'ec2stuff': 'is good'}
        datasource.persist_instance_data()
        instance_data = util.load_json(util.load_file(json_file))
        self.assertEqual(
            {'ec2stuff': 'is good'},
            instance_data['ds']['ec2_metadata'])

    def test_persist_instance_data_writes_network_json_when_set(self):
        """When network_data.json class attribute is set, persist to json."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        instance_data = util.load_json(util.load_file(json_file))
        self.assertNotIn('network_json', instance_data['ds'])
        datasource.network_json = {'network_json': 'is good'}
        datasource.persist_instance_data()
        instance_data = util.load_json(util.load_file(json_file))
        self.assertEqual(
            {'network_json': 'is good'},
            instance_data['ds']['network_json'])

    @skipIf(not six.PY3, "json serialization on <= py2.7 handles bytes")
    def test_get_data_base64encodes_unserializable_bytes(self):
        """On py3, get_data base64encodes any unserializable content."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_metadata={'key1': 'val1', 'key2': {'key2.1': b'\x123'}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        instance_json = util.load_json(content)
        self.assertItemsEqual(
            ['ds/meta_data/key2/key2.1'],
            instance_json['base64_encoded_keys'])
        self.assertEqual(
            {'key1': 'val1', 'key2': {'key2.1': 'EjM='}},
            instance_json['ds']['meta_data'])

    @skipIf(not six.PY2, "json serialization on <= py2.7 handles bytes")
    def test_get_data_handles_bytes_values(self):
        """On py2 get_data handles bytes values without having to b64encode."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_metadata={'key1': 'val1', 'key2': {'key2.1': b'\x123'}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        instance_json = util.load_json(content)
        self.assertEqual([], instance_json['base64_encoded_keys'])
        self.assertEqual(
            {'key1': 'val1', 'key2': {'key2.1': '\x123'}},
            instance_json['ds']['meta_data'])

    @skipIf(not six.PY2, "Only python2 hits UnicodeDecodeErrors on non-utf8")
    def test_non_utf8_encoding_logs_warning(self):
        """When non-utf-8 values exist in py2 instance-data is not written."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_metadata={'key1': 'val1', 'key2': {'key2.1': b'ab\xaadef'}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        self.assertFalse(os.path.exists(json_file))
        self.assertIn(
            "WARNING: Error persisting instance-data.json: 'utf8' codec can't"
            " decode byte 0xaa in position 2: invalid start byte",
            self.logs.getvalue())

    def test_get_hostname_subclass_support(self):
        """Validate get_hostname signature on all subclasses of DataSource."""
        # Use inspect.getfullargspec when we drop py2.6 and py2.7
        get_args = inspect.getargspec  # pylint: disable=W1505
        base_args = get_args(DataSource.get_hostname)  # pylint: disable=W1505
        # Import all DataSource subclasses so we can inspect them.
        modules = util.find_modules(os.path.dirname(os.path.dirname(__file__)))
        for _loc, name in modules.items():
            mod_locs, _ = importer.find_module(name, ['cloudinit.sources'], [])
            if mod_locs:
                importer.import_module(mod_locs[0])
        for child in DataSource.__subclasses__():
            if 'Test' in child.dsname:
                continue
            self.assertEqual(
                base_args,
                get_args(child.get_hostname),  # pylint: disable=W1505
                '%s does not implement DataSource.get_hostname params'
                % child)
            for grandchild in child.__subclasses__():
                self.assertEqual(
                    base_args,
                    get_args(grandchild.get_hostname),  # pylint: disable=W1505
                    '%s does not implement DataSource.get_hostname params'
                    % grandchild)

    def test_clear_cached_attrs_resets_cached_attr_class_attributes(self):
        """Class attributes listed in cached_attr_defaults are reset."""
        count = 0
        # Setup values for all cached class attributes
        for attr, value in self.datasource.cached_attr_defaults:
            setattr(self.datasource, attr, count)
            count += 1
        self.datasource._dirty_cache = True
        self.datasource.clear_cached_attrs()
        for attr, value in self.datasource.cached_attr_defaults:
            self.assertEqual(value, getattr(self.datasource, attr))

    def test_clear_cached_attrs_noops_on_clean_cache(self):
        """Class attributes listed in cached_attr_defaults are reset."""
        count = 0
        # Setup values for all cached class attributes
        for attr, _ in self.datasource.cached_attr_defaults:
            setattr(self.datasource, attr, count)
            count += 1
        self.datasource._dirty_cache = False   # Fake clean cache
        self.datasource.clear_cached_attrs()
        count = 0
        for attr, _ in self.datasource.cached_attr_defaults:
            self.assertEqual(count, getattr(self.datasource, attr))
            count += 1

    def test_clear_cached_attrs_skips_non_attr_class_attributes(self):
        """Skip any cached_attr_defaults which aren't class attributes."""
        self.datasource._dirty_cache = True
        self.datasource.clear_cached_attrs()
        for attr in ('ec2_metadata', 'network_json'):
            self.assertFalse(hasattr(self.datasource, attr))

    def test_clear_cached_attrs_of_custom_attrs(self):
        """Custom attr_values can be passed to clear_cached_attrs."""
        self.datasource._dirty_cache = True
        cached_attr_name = self.datasource.cached_attr_defaults[0][0]
        setattr(self.datasource, cached_attr_name, 'himom')
        self.datasource.myattr = 'orig'
        self.datasource.clear_cached_attrs(
            attr_defaults=(('myattr', 'updated'),))
        self.assertEqual('himom', getattr(self.datasource, cached_attr_name))
        self.assertEqual('updated', self.datasource.myattr)

    def test_update_metadata_only_acts_on_supported_update_events(self):
        """update_metadata won't get_data on unsupported update events."""
        self.datasource.update_events['network'].discard(EventType.BOOT)
        self.assertEqual(
            {'network': set([EventType.BOOT_NEW_INSTANCE])},
            self.datasource.update_events)

        def fake_get_data():
            raise Exception('get_data should not be called')

        self.datasource.get_data = fake_get_data
        self.assertFalse(
            self.datasource.update_metadata(
                source_event_types=[EventType.BOOT]))

    def test_update_metadata_returns_true_on_supported_update_event(self):
        """update_metadata returns get_data response on supported events."""

        def fake_get_data():
            return True

        self.datasource.get_data = fake_get_data
        self.datasource._network_config = 'something'
        self.datasource._dirty_cache = True
        self.assertTrue(
            self.datasource.update_metadata(
                source_event_types=[
                    EventType.BOOT, EventType.BOOT_NEW_INSTANCE]))
        self.assertEqual(UNSET, self.datasource._network_config)
        self.assertIn(
            "DEBUG: Update datasource metadata and network config due to"
            " events: New instance first boot",
            self.logs.getvalue())


class TestRedactSensitiveData(CiTestCase):

    def test_redact_sensitive_data_noop_when_no_sensitive_keys_present(self):
        """When sensitive_keys is absent or empty from metadata do nothing."""
        md = {'my': 'data'}
        self.assertEqual(
            md, redact_sensitive_keys(md, redact_value='redacted'))
        md['sensitive_keys'] = []
        self.assertEqual(
            md, redact_sensitive_keys(md, redact_value='redacted'))

    def test_redact_sensitive_data_redacts_exact_match_name(self):
        """Only exact matched sensitive_keys are redacted from metadata."""
        md = {'sensitive_keys': ['md/secure'],
              'md': {'secure': 's3kr1t', 'insecure': 'publik'}}
        secure_md = copy.deepcopy(md)
        secure_md['md']['secure'] = 'redacted'
        self.assertEqual(
            secure_md,
            redact_sensitive_keys(md, redact_value='redacted'))

    def test_redact_sensitive_data_does_redacts_with_default_string(self):
        """When redact_value is absent, REDACT_SENSITIVE_VALUE is used."""
        md = {'sensitive_keys': ['md/secure'],
              'md': {'secure': 's3kr1t', 'insecure': 'publik'}}
        secure_md = copy.deepcopy(md)
        secure_md['md']['secure'] = 'redacted for non-root user'
        self.assertEqual(
            secure_md,
            redact_sensitive_keys(md))


class TestCanonicalCloudID(CiTestCase):

    def test_cloud_id_returns_platform_on_unknowns(self):
        """When region and cloud_name are unknown, return platform."""
        self.assertEqual(
            'platform',
            canonical_cloud_id(cloud_name=METADATA_UNKNOWN,
                               region=METADATA_UNKNOWN,
                               platform='platform'))

    def test_cloud_id_returns_platform_on_none(self):
        """When region and cloud_name are unknown, return platform."""
        self.assertEqual(
            'platform',
            canonical_cloud_id(cloud_name=None,
                               region=None,
                               platform='platform'))

    def test_cloud_id_returns_cloud_name_on_unknown_region(self):
        """When region is unknown, return cloud_name."""
        for region in (None, METADATA_UNKNOWN):
            self.assertEqual(
                'cloudname',
                canonical_cloud_id(cloud_name='cloudname',
                                   region=region,
                                   platform='platform'))

    def test_cloud_id_returns_platform_on_unknown_cloud_name(self):
        """When region is set but cloud_name is unknown return cloud_name."""
        self.assertEqual(
            'platform',
            canonical_cloud_id(cloud_name=METADATA_UNKNOWN,
                               region='region',
                               platform='platform'))

    def test_cloud_id_aws_based_on_region_and_cloud_name(self):
        """When cloud_name is aws, return proper cloud-id based on region."""
        self.assertEqual(
            'aws-china',
            canonical_cloud_id(cloud_name='aws',
                               region='cn-north-1',
                               platform='platform'))
        self.assertEqual(
            'aws',
            canonical_cloud_id(cloud_name='aws',
                               region='us-east-1',
                               platform='platform'))
        self.assertEqual(
            'aws-gov',
            canonical_cloud_id(cloud_name='aws',
                               region='us-gov-1',
                               platform='platform'))
        self.assertEqual(  # Overrideen non-aws cloud_name is returned
            '!aws',
            canonical_cloud_id(cloud_name='!aws',
                               region='us-gov-1',
                               platform='platform'))

    def test_cloud_id_azure_based_on_region_and_cloud_name(self):
        """Report cloud-id when cloud_name is azure and region is in china."""
        self.assertEqual(
            'azure-china',
            canonical_cloud_id(cloud_name='azure',
                               region='chinaeast',
                               platform='platform'))
        self.assertEqual(
            'azure',
            canonical_cloud_id(cloud_name='azure',
                               region='!chinaeast',
                               platform='platform'))

# vi: ts=4 expandtab
