# Author: Mathieu Corbin <mathieu.corbin@exoscale.com>
# Author: Christopher Glass <christopher.glass@exoscale.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import os

import requests
import responses

from cloudinit import helpers, util
from cloudinit.sources.DataSourceExoscale import (
    API_VERSION,
    METADATA_URL,
    PASSWORD_SERVER_PORT,
    DataSourceExoscale,
    get_password,
    read_metadata,
)
from tests.unittests.helpers import mock

TEST_PASSWORD_URL = "{}:{}/{}/".format(
    METADATA_URL, PASSWORD_SERVER_PORT, API_VERSION
)

TEST_METADATA_URL = "{}/{}/meta-data/".format(METADATA_URL, API_VERSION)

TEST_USERDATA_URL = "{}/{}/user-data".format(METADATA_URL, API_VERSION)


class TestDatasourceExoscale:
    @responses.activate
    def test_password_saved(self):
        """The password is not set when it is not found
        in the metadata service."""
        responses.add(responses.GET, TEST_PASSWORD_URL, body="saved_password")
        assert not get_password()

    @responses.activate
    def test_password_empty(self):
        """No password is set if the metadata service returns
        an empty string."""
        responses.add(responses.GET, TEST_PASSWORD_URL, body="")
        assert not get_password()

    @responses.activate
    def test_password(self):
        """The password is set to what is found in the metadata
        service."""
        expected_password = "p@ssw0rd"
        responses.add(responses.GET, TEST_PASSWORD_URL, body=expected_password)
        password = get_password()
        assert expected_password == password

    def test_activate_removes_set_passwords_semaphore(self, tmp_path):
        """Allow set_passwords to run every boot by removing the semaphore."""
        path = helpers.Paths({"cloud_dir": str(tmp_path)})
        sem_dir = str(tmp_path / "instance/sem")
        util.ensure_dir(sem_dir)
        sem_file = os.path.join(sem_dir, "config_set_passwords")
        with open(sem_file, "w") as stream:
            stream.write("")
        ds = DataSourceExoscale({}, None, path)
        ds.activate(None, None)
        assert not os.path.exists(sem_file)

    @responses.activate
    def test_get_data(self, tmp_path):
        """The datasource conforms to expected behavior when supplied
        full test data."""
        path = helpers.Paths({"run_dir": str(tmp_path)})
        ds = DataSourceExoscale({}, None, path)
        ds.ds_detect = lambda: True
        expected_password = "p@ssw0rd"
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        responses.add(responses.GET, TEST_USERDATA_URL, body=expected_userdata)
        responses.add(responses.GET, TEST_PASSWORD_URL, body=expected_password)
        responses.add(
            responses.GET,
            TEST_METADATA_URL,
            body="instance-id\nlocal-hostname",
        )
        responses.add(
            responses.GET,
            "{}local-hostname".format(TEST_METADATA_URL),
            body=expected_hostname,
        )
        responses.add(
            responses.GET,
            "{}instance-id".format(TEST_METADATA_URL),
            body=expected_id,
        )
        assert ds._check_and_get_data()
        assert ds.userdata_raw.decode("utf-8") == "#cloud-config"
        assert ds.metadata == {
            "instance-id": expected_id,
            "local-hostname": expected_hostname,
        }
        assert ds.get_config_obj() == {
            "ssh_pwauth": True,
            "password": expected_password,
            "chpasswd": {
                "expire": False,
            },
        }

    @responses.activate
    def test_get_data_saved_password(self, tmp_path):
        """The datasource conforms to expected behavior when saved_password is
        returned by the password server."""
        path = helpers.Paths({"run_dir": str(tmp_path)})
        ds = DataSourceExoscale({}, None, path)
        ds.ds_detect = lambda: True
        expected_answer = "saved_password"
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        responses.add(responses.GET, TEST_USERDATA_URL, body=expected_userdata)
        responses.add(responses.GET, TEST_PASSWORD_URL, body=expected_answer)
        responses.add(
            responses.GET,
            TEST_METADATA_URL,
            body="instance-id\nlocal-hostname",
        )
        responses.add(
            responses.GET,
            "{}local-hostname".format(TEST_METADATA_URL),
            body=expected_hostname,
        )
        responses.add(
            responses.GET,
            "{}instance-id".format(TEST_METADATA_URL),
            body=expected_id,
        )
        assert ds._check_and_get_data()
        assert ds.userdata_raw.decode("utf-8") == "#cloud-config"
        assert ds.metadata == {
            "instance-id": expected_id,
            "local-hostname": expected_hostname,
        }
        assert ds.get_config_obj() == {}

    @responses.activate
    def test_get_data_no_password(self, tmp_path):
        """The datasource conforms to expected behavior when no password is
        returned by the password server."""
        path = helpers.Paths({"run_dir": str(tmp_path)})
        ds = DataSourceExoscale({}, None, path)
        ds.ds_detect = lambda: True
        expected_answer = ""
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        responses.add(responses.GET, TEST_USERDATA_URL, body=expected_userdata)
        responses.add(responses.GET, TEST_PASSWORD_URL, body=expected_answer)
        responses.add(
            responses.GET,
            TEST_METADATA_URL,
            body="instance-id\nlocal-hostname",
        )
        responses.add(
            responses.GET,
            "{}local-hostname".format(TEST_METADATA_URL),
            body=expected_hostname,
        )
        responses.add(
            responses.GET,
            "{}instance-id".format(TEST_METADATA_URL),
            body=expected_id,
        )
        assert ds._check_and_get_data()
        assert ds.userdata_raw.decode("utf-8") == "#cloud-config"
        assert ds.metadata == {
            "instance-id": expected_id,
            "local-hostname": expected_hostname,
        }
        assert ds.get_config_obj() == {}

    @responses.activate
    @mock.patch("cloudinit.sources.DataSourceExoscale.get_password")
    def test_read_metadata_when_password_server_unreachable(self, m_password):
        """The read_metadata function returns partial results in case the
        password server (only) is unreachable."""
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"

        m_password.side_effect = requests.Timeout("Fake Connection Timeout")
        responses.add(responses.GET, TEST_USERDATA_URL, body=expected_userdata)
        responses.add(
            responses.GET,
            TEST_METADATA_URL,
            body="instance-id\nlocal-hostname",
        )
        responses.add(
            responses.GET,
            "{}local-hostname".format(TEST_METADATA_URL),
            body=expected_hostname,
        )
        responses.add(
            responses.GET,
            "{}instance-id".format(TEST_METADATA_URL),
            body=expected_id,
        )

        result = read_metadata()

        assert result.get("password") is None
        assert result.get("user-data").decode("utf-8") == expected_userdata

    def test_non_viable_platform(self, tmp_path):
        """The datasource fails fast when the platform is not viable."""
        path = helpers.Paths({"run_dir": str(tmp_path)})
        ds = DataSourceExoscale({}, None, path)
        ds.ds_detect = lambda: False
        assert not ds._check_and_get_data()
