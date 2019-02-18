# This file is part of cloud-init. See LICENSE file for license information.
from cloudinit import helpers
from cloudinit.sources.DataSourceExoscale import (
    API_VERSION,
    DataSourceExoscale,
    SERVICE_ADDRESS)
from cloudinit.tests.helpers import HttprettyTestCase

import httpretty


@httpretty.activate
class TestDatasourceExoscale(HttprettyTestCase):

    def setUp(self):
        super(TestDatasourceExoscale, self).setUp()
        self.tmp = self.tmp_dir()

        self.password_url = "{}:8080/".format(SERVICE_ADDRESS)
        self.metadata_url = "{}/{}/meta-data/".format(SERVICE_ADDRESS,
                                                      API_VERSION)
        self.userdata_url = "{}/{}/user-data".format(SERVICE_ADDRESS,
                                                     API_VERSION)

    def test_password_saved(self):
        path = helpers.Paths({'run_dir': self.tmp})
        ds = DataSourceExoscale({}, None, path)
        httpretty.register_uri(httpretty.GET,
                               self.password_url,
                               body="saved_password")
        self.assertFalse(ds.get_password())

    def test_password_empty(self):
        path = helpers.Paths({'run_dir': self.tmp})
        ds = DataSourceExoscale({}, None, path)
        httpretty.register_uri(httpretty.GET,
                               self.password_url,
                               body="")
        self.assertFalse(ds.get_password())

    def test_password(self):
        path = helpers.Paths({'run_dir': self.tmp})
        ds = DataSourceExoscale({}, None, path)
        expected_password = "p@ssw0rd"
        httpretty.register_uri(httpretty.GET,
                               self.password_url,
                               body=expected_password)
        password = ds.get_password()
        self.assertEqual(expected_password, password)

    def test_get_data(self):
        path = helpers.Paths({'run_dir': self.tmp})
        ds = DataSourceExoscale({}, None, path)
        expected_password = "p@ssw0rd"
        expected_id = "12345"
        expected_hostname = "myname"
        expected_userdata = "#cloud-config"
        httpretty.register_uri(httpretty.GET,
                               self.userdata_url,
                               body=expected_userdata)
        httpretty.register_uri(httpretty.GET,
                               self.password_url,
                               body=expected_password)
        httpretty.register_uri(httpretty.GET,
                               self.metadata_url,
                               body="instance-id\nlocal-hostname")
        httpretty.register_uri(httpretty.GET,
                               "{}local-hostname".format(self.metadata_url),
                               body=expected_hostname)
        httpretty.register_uri(httpretty.GET,
                               "{}local-hostname".format(self.metadata_url),
                               body=expected_hostname)
        httpretty.register_uri(httpretty.GET,
                               "{}instance-id".format(self.metadata_url),
                               body=expected_id)
        ds._get_data()
        self.assertEqual(ds.userdata_raw.decode("utf-8"), "#cloud-config")
        self.assertEqual(ds.metadata, {"instance-id": expected_id,
                                       "local-hostname": expected_hostname})
        self.assertEqual(ds.get_config_obj(),
                         {'ssh_pwauth': True,
                          'password': expected_password,
                          'chpasswd': {
                              'expire': False,
                          }})
