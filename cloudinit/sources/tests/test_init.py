# This file is part of cloud-init. See LICENSE file for license information.

import inspect
import os
import six
import stat

from cloudinit.event import EventType
from cloudinit.helpers import Paths
from cloudinit import importer
from cloudinit.sources import (
    INSTANCE_JSON_FILE, DataSource, UNSET)
from cloudinit.tests.helpers import CiTestCase, skipIf, mock
from cloudinit.user_data import UserDataProcessor
from cloudinit import util


class DataSourceTestSubclassNet(DataSource):

    dsname = 'MyTestSubclass'
    url_max_wait = 55

    def __init__(self, sys_cfg, distro, paths, custom_userdata=None):
        super(DataSourceTestSubclassNet, self).__init__(
            sys_cfg, distro, paths)
        self._custom_userdata = custom_userdata

    def _get_cloud_name(self):
        return 'SubclassCloudName'

    def _get_data(self):
        self.metadata = {'availability_zone': 'myaz',
                         'local-hostname': 'test-subclass-hostname',
                         'region': 'myregion'}
        if self._custom_userdata:
            self.userdata_raw = self._custom_userdata
        else:
            self.userdata_raw = 'userdata_raw'
        self.vendordata_raw = 'vendordata_raw'
        return True


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

    def test_get_data_write_json_instance_data(self):
        """get_data writes INSTANCE_JSON_FILE to run_dir as readonly root."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}))
        datasource.get_data()
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        expected = {
            'base64-encoded-keys': [],
            'v1': {
                'availability-zone': 'myaz',
                'cloud-name': 'subclasscloudname',
                'instance-id': 'iid-datasource',
                'local-hostname': 'test-subclass-hostname',
                'region': 'myregion'},
            'ds': {
                'meta-data': {'availability_zone': 'myaz',
                              'local-hostname': 'test-subclass-hostname',
                              'region': 'myregion'},
                'user-data': 'userdata_raw',
                'vendor-data': 'vendordata_raw'}}
        self.assertEqual(expected, util.load_json(content))
        file_stat = os.stat(json_file)
        self.assertEqual(0o600, stat.S_IMODE(file_stat.st_mode))

    def test_get_data_handles_redacted_unserializable_content(self):
        """get_data warns unserializable content in INSTANCE_JSON_FILE."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_userdata={'key1': 'val1', 'key2': {'key2.1': self.paths}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        expected_userdata = {
            'key1': 'val1',
            'key2': {
                'key2.1': "Warning: redacted unserializable type <class"
                          " 'cloudinit.helpers.Paths'>"}}
        instance_json = util.load_json(content)
        self.assertEqual(
            expected_userdata, instance_json['ds']['user-data'])

    @skipIf(not six.PY3, "json serialization on <= py2.7 handles bytes")
    def test_get_data_base64encodes_unserializable_bytes(self):
        """On py3, get_data base64encodes any unserializable content."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_userdata={'key1': 'val1', 'key2': {'key2.1': b'\x123'}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        instance_json = util.load_json(content)
        self.assertEqual(
            ['ds/user-data/key2/key2.1'],
            instance_json['base64-encoded-keys'])
        self.assertEqual(
            {'key1': 'val1', 'key2': {'key2.1': 'EjM='}},
            instance_json['ds']['user-data'])

    @skipIf(not six.PY2, "json serialization on <= py2.7 handles bytes")
    def test_get_data_handles_bytes_values(self):
        """On py2 get_data handles bytes values without having to b64encode."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_userdata={'key1': 'val1', 'key2': {'key2.1': b'\x123'}})
        self.assertTrue(datasource.get_data())
        json_file = self.tmp_path(INSTANCE_JSON_FILE, tmp)
        content = util.load_file(json_file)
        instance_json = util.load_json(content)
        self.assertEqual([], instance_json['base64-encoded-keys'])
        self.assertEqual(
            {'key1': 'val1', 'key2': {'key2.1': '\x123'}},
            instance_json['ds']['user-data'])

    @skipIf(not six.PY2, "Only python2 hits UnicodeDecodeErrors on non-utf8")
    def test_non_utf8_encoding_logs_warning(self):
        """When non-utf-8 values exist in py2 instance-data is not written."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({'run_dir': tmp}),
            custom_userdata={'key1': 'val1', 'key2': {'key2.1': b'ab\xaadef'}})
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
        self.assertEqual(
            {'network': [EventType.BOOT_NEW_INSTANCE]},
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


# vi: ts=4 expandtab
