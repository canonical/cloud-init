# This file is part of cloud-init. See LICENSE file for license information.

import copy
import inspect
import os
import stat

from cloudinit import importer, util
from cloudinit.distros import ubuntu
from cloudinit.event import EventScope, EventType
from cloudinit.helpers import Paths
from cloudinit.sources import (
    EXPERIMENTAL_TEXT,
    METADATA_UNKNOWN,
    REDACT_SENSITIVE_VALUE,
    UNSET,
    DataSource,
    canonical_cloud_id,
    pkl_load,
    redact_sensitive_keys,
)
from cloudinit.user_data import UserDataProcessor
from tests.unittests.helpers import CiTestCase, mock


class DataSourceTestSubclassNet(DataSource):

    dsname = "MyTestSubclass"
    url_max_wait = 55

    def __init__(
        self,
        sys_cfg,
        distro,
        paths,
        custom_metadata=None,
        custom_userdata=None,
        get_data_retval=True,
    ):
        super(DataSourceTestSubclassNet, self).__init__(sys_cfg, distro, paths)
        self._custom_userdata = custom_userdata
        self._custom_metadata = custom_metadata
        self._get_data_retval = get_data_retval

    def _get_cloud_name(self):
        return "SubclassCloudName"

    def _get_data(self):
        if self._custom_metadata:
            self.metadata = self._custom_metadata
        else:
            self.metadata = {
                "availability_zone": "myaz",
                "local-hostname": "test-subclass-hostname",
                "region": "myregion",
            }
        if self._custom_userdata:
            self.userdata_raw = self._custom_userdata
        else:
            self.userdata_raw = "userdata_raw"
        self.vendordata_raw = "vendordata_raw"
        return self._get_data_retval


class InvalidDataSourceTestSubclassNet(DataSource):
    pass


class TestDataSource(CiTestCase):

    with_logs = True
    maxDiff = None

    def setUp(self):
        super(TestDataSource, self).setUp()
        self.sys_cfg = {"datasource": {"_undef": {"key1": False}}}
        self.distro = ubuntu.Distro("somedistro", {}, {})
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
        self.assertEqual({"key1": False}, self.datasource.ds_cfg)
        self.assertIsInstance(self.datasource.ud_proc, UserDataProcessor)

    def test_datasource_init_gets_ds_cfg_using_dsname(self):
        """Init uses DataSource.dsname for sourcing ds_cfg."""
        sys_cfg = {"datasource": {"MyTestSubclass": {"key2": False}}}
        distro = "distrotest"  # generally should be a Distro object
        datasource = DataSourceTestSubclassNet(sys_cfg, distro, self.paths)
        self.assertEqual({"key2": False}, datasource.ds_cfg)

    def test_str_is_classname(self):
        """The string representation of the datasource is the classname."""
        self.assertEqual("DataSource", str(self.datasource))
        self.assertEqual(
            "DataSourceTestSubclassNet",
            str(DataSourceTestSubclassNet("", "", self.paths)),
        )

    def test_datasource_get_url_params_defaults(self):
        """get_url_params default url config settings for the datasource."""
        params = self.datasource.get_url_params()
        self.assertEqual(params.max_wait_seconds, self.datasource.url_max_wait)
        self.assertEqual(params.timeout_seconds, self.datasource.url_timeout)
        self.assertEqual(params.num_retries, self.datasource.url_retries)
        self.assertEqual(
            params.sec_between_retries, self.datasource.url_sec_between_retries
        )

    def test_datasource_get_url_params_subclassed(self):
        """Subclasses can override get_url_params defaults."""
        sys_cfg = {"datasource": {"MyTestSubclass": {"key2": False}}}
        distro = "distrotest"  # generally should be a Distro object
        datasource = DataSourceTestSubclassNet(sys_cfg, distro, self.paths)
        expected = (
            datasource.url_max_wait,
            datasource.url_timeout,
            datasource.url_retries,
            datasource.url_sec_between_retries,
        )
        url_params = datasource.get_url_params()
        self.assertNotEqual(self.datasource.get_url_params(), url_params)
        self.assertEqual(expected, url_params)

    def test_datasource_get_url_params_ds_config_override(self):
        """Datasource configuration options can override url param defaults."""
        sys_cfg = {
            "datasource": {
                "MyTestSubclass": {
                    "max_wait": "1",
                    "timeout": "2",
                    "retries": "3",
                    "sec_between_retries": 4,
                }
            }
        }
        datasource = DataSourceTestSubclassNet(
            sys_cfg, self.distro, self.paths
        )
        expected = (1, 2, 3, 4)
        url_params = datasource.get_url_params()
        self.assertNotEqual(
            (
                datasource.url_max_wait,
                datasource.url_timeout,
                datasource.url_retries,
                datasource.url_sec_between_retries,
            ),
            url_params,
        )
        self.assertEqual(expected, url_params)

    def test_datasource_get_url_params_is_zero_or_greater(self):
        """get_url_params ignores timeouts with a value below 0."""
        # Set an override that is below 0 which gets ignored.
        sys_cfg = {"datasource": {"_undef": {"timeout": "-1"}}}
        datasource = DataSource(sys_cfg, self.distro, self.paths)
        (
            _max_wait,
            timeout,
            _retries,
            _sec_between_retries,
        ) = datasource.get_url_params()
        self.assertEqual(0, timeout)

    def test_datasource_get_url_uses_defaults_on_errors(self):
        """On invalid system config values for url_params defaults are used."""
        # All invalid values should be logged
        sys_cfg = {
            "datasource": {
                "_undef": {
                    "max_wait": "nope",
                    "timeout": "bug",
                    "retries": "nonint",
                }
            }
        }
        datasource = DataSource(sys_cfg, self.distro, self.paths)
        url_params = datasource.get_url_params()
        expected = (
            datasource.url_max_wait,
            datasource.url_timeout,
            datasource.url_retries,
            datasource.url_sec_between_retries,
        )
        self.assertEqual(expected, url_params)
        logs = self.logs.getvalue()
        expected_logs = [
            "Config max_wait 'nope' is not an int, using default '-1'",
            "Config timeout 'bug' is not an int, using default '10'",
            "Config retries 'nonint' is not an int, using default '5'",
        ]
        for log in expected_logs:
            self.assertIn(log, logs)

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    def test_fallback_interface_is_discovered(self, m_get_fallback_nic):
        """The fallback_interface is discovered via find_fallback_nic."""
        m_get_fallback_nic.return_value = "nic9"
        self.assertEqual("nic9", self.datasource.distro.fallback_interface)

    @mock.patch("cloudinit.sources.net.find_fallback_nic")
    def test_fallback_interface_logs_undiscovered(self, m_get_fallback_nic):
        """Log a warning when fallback_interface can not discover the nic."""
        m_get_fallback_nic.return_value = None  # Couldn't discover nic
        self.assertIsNone(self.datasource.distro.fallback_interface)
        self.assertEqual(
            "WARNING: Did not find a fallback interface on distro: "
            "somedistro.\n",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.sources.net.find_fallback_nic")
    def test_wb_fallback_interface_is_cached(self, m_get_fallback_nic):
        """The fallback_interface is cached and won't be rediscovered."""
        self.datasource.distro.fallback_interface = "nic10"
        self.assertEqual("nic10", self.datasource.distro.fallback_interface)
        m_get_fallback_nic.assert_not_called()

    def test__get_data_unimplemented(self):
        """Raise an error when _get_data is not implemented."""
        with self.assertRaises(NotImplementedError) as context_manager:
            self.datasource.get_data()
        self.assertIn(
            "Subclasses of DataSource must implement _get_data",
            str(context_manager.exception),
        )
        datasource2 = InvalidDataSourceTestSubclassNet(
            self.sys_cfg, self.distro, self.paths
        )
        with self.assertRaises(NotImplementedError) as context_manager:
            datasource2.get_data()
        self.assertIn(
            "Subclasses of DataSource must implement _get_data",
            str(context_manager.exception),
        )

    def test_get_data_calls_subclass__get_data(self):
        """Datasource.get_data uses the subclass' version of _get_data."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertTrue(datasource.get_data())
        self.assertEqual(
            {
                "availability_zone": "myaz",
                "local-hostname": "test-subclass-hostname",
                "region": "myregion",
            },
            datasource.metadata,
        )
        self.assertEqual("userdata_raw", datasource.userdata_raw)
        self.assertEqual("vendordata_raw", datasource.vendordata_raw)

    def test_get_hostname_strips_local_hostname_without_domain(self):
        """Datasource.get_hostname strips metadata local-hostname of domain."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertTrue(datasource.get_data())
        self.assertEqual(
            "test-subclass-hostname", datasource.metadata["local-hostname"]
        )
        self.assertEqual(
            "test-subclass-hostname", datasource.get_hostname().hostname
        )
        datasource.metadata["local-hostname"] = "hostname.my.domain.com"
        self.assertEqual("hostname", datasource.get_hostname().hostname)

    def test_get_hostname_with_fqdn_returns_local_hostname_with_domain(self):
        """Datasource.get_hostname with fqdn set gets qualified hostname."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertTrue(datasource.get_data())
        datasource.metadata["local-hostname"] = "hostname.my.domain.com"
        self.assertEqual(
            "hostname.my.domain.com",
            datasource.get_hostname(fqdn=True).hostname,
        )

    def test_get_hostname_without_metadata_uses_system_hostname(self):
        """Datasource.gethostname runs util.get_hostname when no metadata."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = "cloudinit.sources.util.get_fqdn_from_hosts"
        with mock.patch("cloudinit.sources.util.get_hostname") as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                m_gethost.return_value = "systemhostname.domain.com"
                m_fqdn.return_value = None  # No maching fqdn in /etc/hosts
                self.assertEqual(
                    "systemhostname", datasource.get_hostname().hostname
                )
                self.assertEqual(
                    "systemhostname.domain.com",
                    datasource.get_hostname(fqdn=True).hostname,
                )

    def test_get_hostname_without_metadata_returns_none(self):
        """Datasource.gethostname returns None when metadata_only and no MD."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = "cloudinit.sources.util.get_fqdn_from_hosts"
        with mock.patch("cloudinit.sources.util.get_hostname") as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                self.assertIsNone(
                    datasource.get_hostname(metadata_only=True).hostname
                )
                self.assertIsNone(
                    datasource.get_hostname(
                        fqdn=True, metadata_only=True
                    ).hostname
                )
        self.assertEqual([], m_gethost.call_args_list)
        self.assertEqual([], m_fqdn.call_args_list)

    def test_get_hostname_without_metadata_prefers_etc_hosts(self):
        """Datasource.gethostname prefers /etc/hosts to util.get_hostname."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        self.assertEqual({}, datasource.metadata)
        mock_fqdn = "cloudinit.sources.util.get_fqdn_from_hosts"
        with mock.patch("cloudinit.sources.util.get_hostname") as m_gethost:
            with mock.patch(mock_fqdn) as m_fqdn:
                m_gethost.return_value = "systemhostname.domain.com"
                m_fqdn.return_value = "fqdnhostname.domain.com"
                self.assertEqual(
                    "fqdnhostname", datasource.get_hostname().hostname
                )
                self.assertEqual(
                    "fqdnhostname.domain.com",
                    datasource.get_hostname(fqdn=True).hostname,
                )

    def test_get_data_does_not_write_instance_data_on_failure(self):
        """get_data does not write INSTANCE_JSON_FILE on get_data False."""
        tmp = self.tmp_dir()
        paths = Paths({"run_dir": tmp})
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            paths,
            get_data_retval=False,
        )
        self.assertFalse(datasource.get_data())
        json_file = paths.get_runpath("instance_data")
        self.assertFalse(
            os.path.exists(json_file), f"Found unexpected file {json_file}"
        )

    def test_get_data_writes_json_instance_data_on_success(self):
        """get_data writes INSTANCE_JSON_FILE to run_dir as world readable."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg, self.distro, Paths({"run_dir": tmp})
        )
        sys_info = {
            "python": "3.7",
            "platform": (
                "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
            ),
            "uname": [
                "Linux",
                "myhost",
                "5.4.0-24-generic",
                "SMP blah",
                "x86_64",
            ],
            "variant": "ubuntu",
            "dist": ["ubuntu", "20.04", "focal"],
        }
        with mock.patch("cloudinit.util.system_info", return_value=sys_info):
            with mock.patch(
                "cloudinit.sources.canonical_cloud_id",
                return_value="canonical_cloud_id",
            ):
                datasource.get_data()
        json_file = Paths({"run_dir": tmp}).get_runpath("instance_data")
        content = util.load_text_file(json_file)
        expected = {
            "base64_encoded_keys": [],
            "merged_cfg": REDACT_SENSITIVE_VALUE,
            "merged_system_cfg": REDACT_SENSITIVE_VALUE,
            "sensitive_keys": ["merged_cfg", "merged_system_cfg"],
            "sys_info": sys_info,
            "v1": {
                "_beta_keys": ["subplatform"],
                "availability-zone": "myaz",
                "availability_zone": "myaz",
                "cloud_id": "canonical_cloud_id",
                "cloud-name": "subclasscloudname",
                "cloud_name": "subclasscloudname",
                "distro": "ubuntu",
                "distro_release": "focal",
                "distro_version": "20.04",
                "instance-id": "iid-datasource",
                "instance_id": "iid-datasource",
                "local-hostname": "test-subclass-hostname",
                "local_hostname": "test-subclass-hostname",
                "kernel_release": "5.4.0-24-generic",
                "machine": "x86_64",
                "platform": "mytestsubclass",
                "public_ssh_keys": [],
                "python_version": "3.7",
                "region": "myregion",
                "system_platform": (
                    "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
                ),
                "subplatform": "unknown",
                "variant": "ubuntu",
            },
            "ds": {
                "_doc": EXPERIMENTAL_TEXT,
                "meta_data": {
                    "availability_zone": "myaz",
                    "local-hostname": "test-subclass-hostname",
                    "region": "myregion",
                },
            },
        }
        self.assertEqual(expected, util.load_json(content))
        file_stat = os.stat(json_file)
        self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))
        self.assertEqual(expected, util.load_json(content))

    def test_get_data_writes_redacted_public_json_instance_data(self):
        """get_data writes redacted content to public INSTANCE_JSON_FILE."""
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            Paths({"run_dir": tmp}),
            custom_metadata={
                "availability_zone": "myaz",
                "local-hostname": "test-subclass-hostname",
                "region": "myregion",
                "some": {
                    "security-credentials": {
                        "cred1": "sekret",
                        "cred2": "othersekret",
                    }
                },
                "someother": {
                    "nested": {
                        "userData": "HIDE ME",
                    }
                },
                "VENDOR-DAta": "HIDE ME TOO",
            },
        )
        self.assertCountEqual(
            (
                "combined_cloud_config",
                "merged_cfg",
                "merged_system_cfg",
                "security-credentials",
                "userdata",
                "user-data",
                "user_data",
                "vendordata",
                "vendor-data",
                "ds/vendor_data",
            ),
            datasource.sensitive_metadata_keys,
        )
        sys_info = {
            "python": "3.7",
            "platform": (
                "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
            ),
            "uname": [
                "Linux",
                "myhost",
                "5.4.0-24-generic",
                "SMP blah",
                "x86_64",
            ],
            "variant": "ubuntu",
            "dist": ["ubuntu", "20.04", "focal"],
        }
        with mock.patch("cloudinit.util.system_info", return_value=sys_info):
            datasource.get_data()
        json_file = Paths({"run_dir": tmp}).get_runpath("instance_data")
        redacted = util.load_json(util.load_text_file(json_file))
        expected = {
            "base64_encoded_keys": [],
            "merged_cfg": REDACT_SENSITIVE_VALUE,
            "merged_system_cfg": REDACT_SENSITIVE_VALUE,
            "sensitive_keys": [
                "ds/meta_data/VENDOR-DAta",
                "ds/meta_data/some/security-credentials",
                "ds/meta_data/someother/nested/userData",
                "merged_cfg",
                "merged_system_cfg",
            ],
            "sys_info": sys_info,
            "v1": {
                "_beta_keys": ["subplatform"],
                "availability-zone": "myaz",
                "availability_zone": "myaz",
                "cloud-name": "subclasscloudname",
                "cloud_name": "subclasscloudname",
                "cloud_id": "subclasscloudname",
                "distro": "ubuntu",
                "distro_release": "focal",
                "distro_version": "20.04",
                "instance-id": "iid-datasource",
                "instance_id": "iid-datasource",
                "local-hostname": "test-subclass-hostname",
                "local_hostname": "test-subclass-hostname",
                "kernel_release": "5.4.0-24-generic",
                "machine": "x86_64",
                "platform": "mytestsubclass",
                "public_ssh_keys": [],
                "python_version": "3.7",
                "region": "myregion",
                "system_platform": (
                    "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
                ),
                "subplatform": "unknown",
                "variant": "ubuntu",
            },
            "ds": {
                "_doc": EXPERIMENTAL_TEXT,
                "meta_data": {
                    "VENDOR-DAta": REDACT_SENSITIVE_VALUE,
                    "availability_zone": "myaz",
                    "local-hostname": "test-subclass-hostname",
                    "region": "myregion",
                    "some": {"security-credentials": REDACT_SENSITIVE_VALUE},
                    "someother": {
                        "nested": {"userData": REDACT_SENSITIVE_VALUE}
                    },
                },
            },
        }
        self.assertEqual(expected, redacted)
        file_stat = os.stat(json_file)
        self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))

    def test_get_data_writes_json_instance_data_sensitive(self):
        """
        get_data writes unmodified data to sensitive file as root-readonly.
        """
        tmp = self.tmp_dir()
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            Paths({"run_dir": tmp}),
            custom_metadata={
                "availability_zone": "myaz",
                "local-hostname": "test-subclass-hostname",
                "region": "myregion",
                "some": {
                    "security-credentials": {
                        "cred1": "sekret",
                        "cred2": "othersekret",
                    }
                },
            },
        )
        sys_info = {
            "python": "3.7",
            "platform": (
                "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
            ),
            "uname": [
                "Linux",
                "myhost",
                "5.4.0-24-generic",
                "SMP blah",
                "x86_64",
            ],
            "variant": "ubuntu",
            "dist": ["ubuntu", "20.04", "focal"],
        }

        self.assertCountEqual(
            (
                "combined_cloud_config",
                "merged_cfg",
                "merged_system_cfg",
                "security-credentials",
                "userdata",
                "user-data",
                "user_data",
                "vendordata",
                "vendor-data",
                "ds/vendor_data",
            ),
            datasource.sensitive_metadata_keys,
        )
        with mock.patch("cloudinit.util.system_info", return_value=sys_info):
            with mock.patch(
                "cloudinit.sources.canonical_cloud_id",
                return_value="canonical-cloud-id",
            ):
                datasource.get_data()
        sensitive_json_file = Paths({"run_dir": tmp}).get_runpath(
            "instance_data_sensitive"
        )
        content = util.load_text_file(sensitive_json_file)
        expected = {
            "base64_encoded_keys": [],
            "merged_cfg": {
                "_doc": (
                    "DEPRECATED: Use merged_system_cfg. Will be dropped "
                    "from 24.1"
                ),
                "datasource": {"_undef": {"key1": False}},
            },
            "merged_system_cfg": {
                "_doc": (
                    "Merged cloud-init system config from "
                    "/etc/cloud/cloud.cfg and /etc/cloud/cloud.cfg.d/"
                ),
                "datasource": {"_undef": {"key1": False}},
            },
            "sensitive_keys": [
                "ds/meta_data/some/security-credentials",
                "merged_cfg",
                "merged_system_cfg",
            ],
            "sys_info": sys_info,
            "v1": {
                "_beta_keys": ["subplatform"],
                "availability-zone": "myaz",
                "availability_zone": "myaz",
                "cloud_id": "canonical-cloud-id",
                "cloud-name": "subclasscloudname",
                "cloud_name": "subclasscloudname",
                "distro": "ubuntu",
                "distro_release": "focal",
                "distro_version": "20.04",
                "instance-id": "iid-datasource",
                "instance_id": "iid-datasource",
                "kernel_release": "5.4.0-24-generic",
                "local-hostname": "test-subclass-hostname",
                "local_hostname": "test-subclass-hostname",
                "machine": "x86_64",
                "platform": "mytestsubclass",
                "public_ssh_keys": [],
                "python_version": "3.7",
                "region": "myregion",
                "subplatform": "unknown",
                "system_platform": (
                    "Linux-5.4.0-24-generic-x86_64-with-Ubuntu-20.04-focal"
                ),
                "variant": "ubuntu",
            },
            "ds": {
                "_doc": EXPERIMENTAL_TEXT,
                "meta_data": {
                    "availability_zone": "myaz",
                    "local-hostname": "test-subclass-hostname",
                    "region": "myregion",
                    "some": {
                        "security-credentials": {
                            "cred1": "sekret",
                            "cred2": "othersekret",
                        }
                    },
                },
            },
        }
        self.assertCountEqual(expected, util.load_json(content))
        file_stat = os.stat(sensitive_json_file)
        self.assertEqual(0o600, stat.S_IMODE(file_stat.st_mode))
        self.assertEqual(expected, util.load_json(content))

    def test_get_data_handles_redacted_unserializable_content(self):
        """get_data warns unserializable content in INSTANCE_JSON_FILE."""
        tmp = self.tmp_dir()
        paths = Paths({"run_dir": tmp})
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            paths,
            custom_metadata={"key1": "val1", "key2": {"key2.1": self.paths}},
        )
        datasource.get_data()
        json_file = paths.get_runpath("instance_data")
        content = util.load_text_file(json_file)
        expected_metadata = {
            "key1": "val1",
            "key2": {
                "key2.1": (
                    "Warning: redacted unserializable type <class"
                    " 'cloudinit.helpers.Paths'>"
                )
            },
        }
        instance_json = util.load_json(content)
        self.assertEqual(expected_metadata, instance_json["ds"]["meta_data"])

    def test_persist_instance_data_writes_ec2_metadata_when_set(self):
        """When ec2_metadata class attribute is set, persist to json."""
        tmp = self.tmp_dir()
        cloud_dir = os.path.join(tmp, "cloud")
        util.ensure_dir(cloud_dir)
        paths = Paths({"run_dir": tmp, "cloud_dir": cloud_dir})
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            paths,
        )
        datasource.ec2_metadata = UNSET
        datasource.get_data()
        json_file = paths.get_runpath("instance_data")
        instance_data = util.load_json(util.load_text_file(json_file))
        self.assertNotIn("ec2_metadata", instance_data["ds"])
        datasource.ec2_metadata = {"ec2stuff": "is good"}
        datasource.persist_instance_data()
        instance_data = util.load_json(util.load_text_file(json_file))
        self.assertEqual(
            {"ec2stuff": "is good"}, instance_data["ds"]["ec2_metadata"]
        )

    def test_persist_instance_data_writes_canonical_cloud_id_and_symlink(self):
        """canonical-cloud-id class attribute is set, persist to json."""
        tmp = self.tmp_dir()
        cloud_dir = os.path.join(tmp, "cloud")
        util.ensure_dir(cloud_dir)
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            Paths({"run_dir": tmp, "cloud_dir": cloud_dir}),
        )
        cloud_id_link = os.path.join(tmp, "cloud-id")
        cloud_id_file = os.path.join(tmp, "cloud-id-my-cloud")
        cloud_id2_file = os.path.join(tmp, "cloud-id-my-cloud2")
        for filename in (cloud_id_file, cloud_id_link, cloud_id2_file):
            self.assertFalse(
                os.path.exists(filename), "Unexpected link found {filename}"
            )
        with mock.patch(
            "cloudinit.sources.canonical_cloud_id", return_value="my-cloud"
        ):
            datasource.get_data()
            self.assertEqual("my-cloud\n", util.load_text_file(cloud_id_link))
            # A symlink with the generic /run/cloud-init/cloud-id
            # link is present
            self.assertTrue(util.is_link(cloud_id_link))
            datasource.persist_instance_data()
            # cloud-id<cloud-type> not deleted: no cloud-id change
            self.assertTrue(os.path.exists(cloud_id_file))
        # When cloud-id changes, symlink and content change
        with mock.patch(
            "cloudinit.sources.canonical_cloud_id", return_value="my-cloud2"
        ):
            datasource.persist_instance_data()
        self.assertEqual("my-cloud2\n", util.load_text_file(cloud_id2_file))
        # Previous cloud-id-<cloud-type> file removed
        self.assertFalse(os.path.exists(cloud_id_file))
        # Generic link persisted which contains canonical-cloud-id as content
        self.assertTrue(util.is_link(cloud_id_link))
        self.assertEqual("my-cloud2\n", util.load_text_file(cloud_id_link))

    def test_persist_instance_data_writes_network_json_when_set(self):
        """When network_data.json class attribute is set, persist to json."""
        tmp = self.tmp_dir()
        cloud_dir = os.path.join(tmp, "cloud")
        util.ensure_dir(cloud_dir)
        paths = Paths({"run_dir": tmp, "cloud_dir": cloud_dir})
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            paths,
        )
        datasource.get_data()
        json_file = paths.get_runpath("instance_data")
        instance_data = util.load_json(util.load_text_file(json_file))
        self.assertNotIn("network_json", instance_data["ds"])
        datasource.network_json = {"network_json": "is good"}
        datasource.persist_instance_data()
        instance_data = util.load_json(util.load_text_file(json_file))
        self.assertEqual(
            {"network_json": "is good"}, instance_data["ds"]["network_json"]
        )

    def test_persist_instance_serializes_datasource_pickle(self):
        """obj.pkl is written when instance link present and write_cache."""
        tmp = self.tmp_dir()
        cloud_dir = os.path.join(tmp, "cloud")
        util.ensure_dir(cloud_dir)
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            Paths({"run_dir": tmp, "cloud_dir": cloud_dir}),
        )
        pkl_cache_file = os.path.join(cloud_dir, "instance/obj.pkl")
        self.assertFalse(os.path.exists(pkl_cache_file))
        datasource.network_json = {"network_json": "is good"}
        # No /var/lib/cloud/instance symlink
        datasource.persist_instance_data(write_cache=True)
        self.assertFalse(os.path.exists(pkl_cache_file))

        # Symlink /var/lib/cloud/instance but write_cache=False
        util.sym_link(cloud_dir, os.path.join(cloud_dir, "instance"))
        datasource.persist_instance_data(write_cache=False)
        self.assertFalse(os.path.exists(pkl_cache_file))

        # Symlink /var/lib/cloud/instance and write_cache=True
        datasource.persist_instance_data(write_cache=True)
        self.assertTrue(os.path.exists(pkl_cache_file))
        ds = pkl_load(pkl_cache_file)
        self.assertEqual(datasource.network_json, ds.network_json)

    def test_get_data_base64encodes_unserializable_bytes(self):
        """On py3, get_data base64encodes any unserializable content."""
        tmp = self.tmp_dir()
        paths = Paths({"run_dir": tmp})
        datasource = DataSourceTestSubclassNet(
            self.sys_cfg,
            self.distro,
            paths,
            custom_metadata={"key1": "val1", "key2": {"key2.1": b"\x123"}},
        )
        self.assertTrue(datasource.get_data())
        json_file = paths.get_runpath("instance_data")
        content = util.load_text_file(json_file)
        instance_json = util.load_json(content)
        self.assertCountEqual(
            ["ds/meta_data/key2/key2.1"], instance_json["base64_encoded_keys"]
        )
        self.assertEqual(
            {"key1": "val1", "key2": {"key2.1": "EjM="}},
            instance_json["ds"]["meta_data"],
        )

    def test_get_hostname_subclass_support(self):
        """Validate get_hostname signature on all subclasses of DataSource."""
        base_args = inspect.getfullargspec(DataSource.get_hostname)
        # Import all DataSource subclasses so we can inspect them.
        modules = util.get_modules_from_dir(
            os.path.dirname(os.path.dirname(__file__))
        )
        for _loc, name in modules.items():
            mod_locs, _ = importer.find_module(name, ["cloudinit.sources"], [])
            if mod_locs:
                importer.import_module(mod_locs[0])
        for child in DataSource.__subclasses__():
            if "Test" in child.dsname:
                continue
            self.assertEqual(
                base_args,
                inspect.getfullargspec(child.get_hostname),
                "%s does not implement DataSource.get_hostname params" % child,
            )
            for grandchild in child.__subclasses__():
                self.assertEqual(
                    base_args,
                    inspect.getfullargspec(grandchild.get_hostname),
                    "%s does not implement DataSource.get_hostname params"
                    % grandchild,
                )

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
        self.datasource._dirty_cache = False  # Fake clean cache
        self.datasource.clear_cached_attrs()
        count = 0
        for attr, _ in self.datasource.cached_attr_defaults:
            self.assertEqual(count, getattr(self.datasource, attr))
            count += 1

    def test_clear_cached_attrs_skips_non_attr_class_attributes(self):
        """Skip any cached_attr_defaults which aren't class attributes."""
        self.datasource._dirty_cache = True
        self.datasource.clear_cached_attrs()
        for attr in ("ec2_metadata", "network_json"):
            self.assertFalse(hasattr(self.datasource, attr))

    def test_clear_cached_attrs_of_custom_attrs(self):
        """Custom attr_values can be passed to clear_cached_attrs."""
        self.datasource._dirty_cache = True
        cached_attr_name = self.datasource.cached_attr_defaults[0][0]
        setattr(self.datasource, cached_attr_name, "himom")
        self.datasource.myattr = "orig"
        self.datasource.clear_cached_attrs(
            attr_defaults=(("myattr", "updated"),)
        )
        self.assertEqual("himom", getattr(self.datasource, cached_attr_name))
        self.assertEqual("updated", self.datasource.myattr)

    @mock.patch.dict(
        DataSource.default_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    @mock.patch.dict(
        DataSource.supported_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_update_metadata_only_acts_on_supported_update_events(self):
        """update_metadata_if_supported wont get_data on unsupported events."""
        self.assertEqual(
            {EventScope.NETWORK: set([EventType.BOOT_NEW_INSTANCE])},
            self.datasource.default_update_events,
        )

        fake_get_data = mock.Mock()
        self.datasource.get_data = fake_get_data
        self.assertFalse(
            self.datasource.update_metadata_if_supported(
                source_event_types=[EventType.BOOT]
            )
        )
        self.assertEqual([], fake_get_data.call_args_list)

    @mock.patch.dict(
        DataSource.supported_update_events,
        {EventScope.NETWORK: {EventType.BOOT_NEW_INSTANCE}},
    )
    def test_update_metadata_returns_true_on_supported_update_event(self):
        """update_metadata_if_supported returns get_data on supported events"""

        def fake_get_data():
            return True

        self.datasource.get_data = fake_get_data
        self.datasource._network_config = "something"
        self.datasource._dirty_cache = True
        self.assertTrue(
            self.datasource.update_metadata_if_supported(
                source_event_types=[
                    EventType.BOOT,
                    EventType.BOOT_NEW_INSTANCE,
                ]
            )
        )
        self.assertEqual(UNSET, self.datasource._network_config)

        self.assertIn(
            "DEBUG: Update datasource metadata and network config due to"
            " events: boot-new-instance",
            self.logs.getvalue(),
        )


class TestRedactSensitiveData(CiTestCase):
    def test_redact_sensitive_data_noop_when_no_sensitive_keys_present(self):
        """When sensitive_keys is absent or empty from metadata do nothing."""
        md = {"my": "data"}
        self.assertEqual(
            md, redact_sensitive_keys(md, redact_value="redacted")
        )
        md["sensitive_keys"] = []
        self.assertEqual(
            md, redact_sensitive_keys(md, redact_value="redacted")
        )

    def test_redact_sensitive_data_redacts_exact_match_name(self):
        """Only exact matched sensitive_keys are redacted from metadata."""
        md = {
            "sensitive_keys": ["md/secure"],
            "md": {"secure": "s3kr1t", "insecure": "publik"},
        }
        secure_md = copy.deepcopy(md)
        secure_md["md"]["secure"] = "redacted"
        self.assertEqual(
            secure_md, redact_sensitive_keys(md, redact_value="redacted")
        )

    def test_redact_sensitive_data_does_redacts_with_default_string(self):
        """When redact_value is absent, REDACT_SENSITIVE_VALUE is used."""
        md = {
            "sensitive_keys": ["md/secure"],
            "md": {"secure": "s3kr1t", "insecure": "publik"},
        }
        secure_md = copy.deepcopy(md)
        secure_md["md"]["secure"] = "redacted for non-root user"
        self.assertEqual(secure_md, redact_sensitive_keys(md))


class TestCanonicalCloudID(CiTestCase):
    def test_cloud_id_returns_platform_on_unknowns(self):
        """When region and cloud_name are unknown, return platform."""
        self.assertEqual(
            "platform",
            canonical_cloud_id(
                cloud_name=METADATA_UNKNOWN,
                region=METADATA_UNKNOWN,
                platform="platform",
            ),
        )

    def test_cloud_id_returns_platform_on_none(self):
        """When region and cloud_name are unknown, return platform."""
        self.assertEqual(
            "platform",
            canonical_cloud_id(
                cloud_name=None, region=None, platform="platform"
            ),
        )

    def test_cloud_id_returns_cloud_name_on_unknown_region(self):
        """When region is unknown, return cloud_name."""
        for region in (None, METADATA_UNKNOWN):
            self.assertEqual(
                "cloudname",
                canonical_cloud_id(
                    cloud_name="cloudname", region=region, platform="platform"
                ),
            )

    def test_cloud_id_returns_platform_on_unknown_cloud_name(self):
        """When region is set but cloud_name is unknown return cloud_name."""
        self.assertEqual(
            "platform",
            canonical_cloud_id(
                cloud_name=METADATA_UNKNOWN,
                region="region",
                platform="platform",
            ),
        )

    def test_cloud_id_aws_based_on_region_and_cloud_name(self):
        """When cloud_name is aws, return proper cloud-id based on region."""
        self.assertEqual(
            "aws-china",
            canonical_cloud_id(
                cloud_name="aws", region="cn-north-1", platform="platform"
            ),
        )
        self.assertEqual(
            "aws",
            canonical_cloud_id(
                cloud_name="aws", region="us-east-1", platform="platform"
            ),
        )
        self.assertEqual(
            "aws-gov",
            canonical_cloud_id(
                cloud_name="aws", region="us-gov-1", platform="platform"
            ),
        )
        self.assertEqual(  # Overrideen non-aws cloud_name is returned
            "!aws",
            canonical_cloud_id(
                cloud_name="!aws", region="us-gov-1", platform="platform"
            ),
        )

    def test_cloud_id_azure_based_on_region_and_cloud_name(self):
        """Report cloud-id when cloud_name is azure and region is in china."""
        self.assertEqual(
            "azure-china",
            canonical_cloud_id(
                cloud_name="azure", region="chinaeast", platform="platform"
            ),
        )
        self.assertEqual(
            "azure",
            canonical_cloud_id(
                cloud_name="azure", region="!chinaeast", platform="platform"
            ),
        )
