# Author: Mathieu Corbin <mathieu.corbin@exoscale.com>
# Author: Christopher Glass <christopher.glass@exoscale.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import os

import httpretty
import requests

from cloudinit import helpers, util
from cloudinit.sources.DataSourceExoscale import (
    API_VERSION,
    METADATA_URL,
    PASSWORD_SERVER_PORT,
    DataSourceExoscale,
    get_password,
    read_metadata,
)
from tests.unittests.helpers import HttprettyTestCase, mock

TEST_PASSWORD_URL = "{}:{}/{}/".format(
    METADATA_URL, PASSWORD_SERVER_PORT, API_VERSION
)

TEST_METADATA_URL = "{}/{}/meta-data/".format(METADATA_URL, API_VERSION)

TEST_USERDATA_URL = "{}/{}/user-data".format(METADATA_URL, API_VERSION)


@httpretty.activate
class TestDatasourceExoscale(HttprettyTestCase):
    def setUp(self):
        super(TestDatasourceExoscale, self).setUp()
        self.tmp = self.tmp_dir()
        self.password_url = TEST_PASSWORD_URL
        self.metadata_url = TEST_METADATA_URL
        self.userdata_url = TEST_USERDATA_URL

    def test_password_saved(self):
        """The password is not set when it is not found
        in the metadata service."""
        httpretty.register_uri(
            httpretty.GET, self.password_url, body="saved_password"
        )
        self.assertFalse(get_password())

    def test_password_empty(self):
        """No password is set if the metadata service returns
        an empty string."""
        httpretty.register_uri(httpretty.GET, self.password_url, body="")
        self.assertFalse(get_password())

    def test_password(self):
        """The password is set to what is found in the metadata
        service."""
        expected_password = "p@ssw0rd"
        httpretty.register_uri(
            httpretty.GET, self.password_url, body=expected_password
        )
        password = get_password()
        self.assertEqual(expected_password, password)

    def test_activate_removes_set_passwords_semaphore(self):
        """Allow set_passwords to run every boot by removing the semaphore."""
        path = helpers.Paths({"cloud_dir": self.tmp})
        sem_dir = self.tmp_path("instance/sem", dir=self.tmp)
        util.ensure_dir(sem_dir)
        sem_file = os.path.join(sem_dir, "config_set_passwords")
        with open(sem_file, "w") as stream:
            stream.write("")
        ds = DataSourceExoscale({}, None, path)
        ds.activate(None, None)
        self.assertFalse(os.path.exists(sem_file))

    def test_get_data(self):
        """The datasource conforms to expected behavior when supplied
        full test data."""
        path = helpers.Paths({"run_dir": self.tmp})
        ds = DataSourceExoscale({}, None, path)
        ds._is_platform_viable = lambda: True
        expected_password = "p@ssw0rd"
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        httpretty.register_uri(
            httpretty.GET, self.userdata_url, body=expected_userdata
        )
        httpretty.register_uri(
            httpretty.GET, self.password_url, body=expected_password
        )
        httpretty.register_uri(
            httpretty.GET,
            self.metadata_url,
            body="instance-id\nlocal-hostname",
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}local-hostname".format(self.metadata_url),
            body=expected_hostname,
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}instance-id".format(self.metadata_url),
            body=expected_id,
        )
        self.assertTrue(ds._get_data())
        self.assertEqual(ds.userdata_raw.decode("utf-8"), "#cloud-config")
        self.assertEqual(
            ds.metadata,
            {"instance-id": expected_id, "local-hostname": expected_hostname},
        )
        self.assertEqual(
            ds.get_config_obj(),
            {
                "ssh_pwauth": True,
                "password": expected_password,
                "chpasswd": {
                    "expire": False,
                },
            },
        )

    def test_get_data_saved_password(self):
        """The datasource conforms to expected behavior when saved_password is
        returned by the password server."""
        path = helpers.Paths({"run_dir": self.tmp})
        ds = DataSourceExoscale({}, None, path)
        ds._is_platform_viable = lambda: True
        expected_answer = "saved_password"
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        httpretty.register_uri(
            httpretty.GET, self.userdata_url, body=expected_userdata
        )
        httpretty.register_uri(
            httpretty.GET, self.password_url, body=expected_answer
        )
        httpretty.register_uri(
            httpretty.GET,
            self.metadata_url,
            body="instance-id\nlocal-hostname",
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}local-hostname".format(self.metadata_url),
            body=expected_hostname,
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}instance-id".format(self.metadata_url),
            body=expected_id,
        )
        self.assertTrue(ds._get_data())
        self.assertEqual(ds.userdata_raw.decode("utf-8"), "#cloud-config")
        self.assertEqual(
            ds.metadata,
            {"instance-id": expected_id, "local-hostname": expected_hostname},
        )
        self.assertEqual(ds.get_config_obj(), {})

    def test_get_data_no_password(self):
        """The datasource conforms to expected behavior when no password is
        returned by the password server."""
        path = helpers.Paths({"run_dir": self.tmp})
        ds = DataSourceExoscale({}, None, path)
        ds._is_platform_viable = lambda: True
        expected_answer = ""
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        httpretty.register_uri(
            httpretty.GET, self.userdata_url, body=expected_userdata
        )
        httpretty.register_uri(
            httpretty.GET, self.password_url, body=expected_answer
        )
        httpretty.register_uri(
            httpretty.GET,
            self.metadata_url,
            body="instance-id\nlocal-hostname",
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}local-hostname".format(self.metadata_url),
            body=expected_hostname,
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}instance-id".format(self.metadata_url),
            body=expected_id,
        )
        self.assertTrue(ds._get_data())
        self.assertEqual(ds.userdata_raw.decode("utf-8"), "#cloud-config")
        self.assertEqual(
            ds.metadata,
            {"instance-id": expected_id, "local-hostname": expected_hostname},
        )
        self.assertEqual(ds.get_config_obj(), {})

    @mock.patch("cloudinit.sources.DataSourceExoscale.get_password")
    def test_read_metadata_when_password_server_unreachable(self, m_password):
        """The read_metadata function returns partial results in case the
        password server (only) is unreachable."""
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"

        m_password.side_effect = requests.Timeout("Fake Connection Timeout")
        httpretty.register_uri(
            httpretty.GET, self.userdata_url, body=expected_userdata
        )
        httpretty.register_uri(
            httpretty.GET,
            self.metadata_url,
            body="instance-id\nlocal-hostname",
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}local-hostname".format(self.metadata_url),
            body=expected_hostname,
        )
        httpretty.register_uri(
            httpretty.GET,
            "{}instance-id".format(self.metadata_url),
            body=expected_id,
        )

        result = read_metadata()

        self.assertIsNone(result.get("password"))
        self.assertEqual(
            result.get("user-data").decode("utf-8"), expected_userdata
        )

    def test_non_viable_platform(self):
        """The datasource fails fast when the platform is not viable."""
        path = helpers.Paths({"run_dir": self.tmp})
        ds = DataSourceExoscale({}, None, path)
        ds._is_platform_viable = lambda: False
        self.assertFalse(ds._get_data())
