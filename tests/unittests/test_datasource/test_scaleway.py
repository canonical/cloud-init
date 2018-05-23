# This file is part of cloud-init. See LICENSE file for license information.

import json

import httpretty
import requests

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceScaleway

from cloudinit.tests.helpers import mock, HttprettyTestCase, CiTestCase


class DataResponses(object):
    """
    Possible responses of the API endpoint
    169.254.42.42/user_data/cloud-init and
    169.254.42.42/vendor_data/cloud-init.
    """

    FAKE_USER_DATA = '#!/bin/bash\necho "user-data"'

    @staticmethod
    def rate_limited(method, uri, headers):
        return 429, headers, ''

    @staticmethod
    def api_error(method, uri, headers):
        return 500, headers, ''

    @classmethod
    def get_ok(cls, method, uri, headers):
        return 200, headers, cls.FAKE_USER_DATA

    @staticmethod
    def empty(method, uri, headers):
        """
        No user data for this server.
        """
        return 404, headers, ''


class MetadataResponses(object):
    """
    Possible responses of the metadata API.
    """

    FAKE_METADATA = {
        'id': '00000000-0000-0000-0000-000000000000',
        'hostname': 'scaleway.host',
        'ssh_public_keys': [{
            'key': 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA',
            'fingerprint': '2048 06:ae:...  login (RSA)'
        }, {
            'key': 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC',
            'fingerprint': '2048 06:ff:...  login2 (RSA)'
        }]
    }

    @classmethod
    def get_ok(cls, method, uri, headers):
        return 200, headers, json.dumps(cls.FAKE_METADATA)


class TestOnScaleway(CiTestCase):

    def setUp(self):
        super(TestOnScaleway, self).setUp()
        self.tmp = self.tmp_dir()

    def install_mocks(self, fake_dmi, fake_file_exists, fake_cmdline):
        mock, faked = fake_dmi
        mock.return_value = 'Scaleway' if faked else 'Whatever'

        mock, faked = fake_file_exists
        mock.return_value = faked

        mock, faked = fake_cmdline
        mock.return_value = \
            'initrd=initrd showopts scaleway nousb' if faked \
            else 'BOOT_IMAGE=/vmlinuz-3.11.0-26-generic'

    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('os.path.exists')
    @mock.patch('cloudinit.util.read_dmi_data')
    def test_not_on_scaleway(self, m_read_dmi_data, m_file_exists,
                             m_get_cmdline):
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, False)
        )
        self.assertFalse(DataSourceScaleway.on_scaleway())

        # When not on Scaleway, get_data() returns False.
        datasource = DataSourceScaleway.DataSourceScaleway(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp})
        )
        self.assertFalse(datasource.get_data())

    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('os.path.exists')
    @mock.patch('cloudinit.util.read_dmi_data')
    def test_on_scaleway_dmi(self, m_read_dmi_data, m_file_exists,
                             m_get_cmdline):
        """
        dmidecode returns "Scaleway".
        """
        # dmidecode returns "Scaleway"
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, True),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, False)
        )
        self.assertTrue(DataSourceScaleway.on_scaleway())

    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('os.path.exists')
    @mock.patch('cloudinit.util.read_dmi_data')
    def test_on_scaleway_var_run_scaleway(self, m_read_dmi_data, m_file_exists,
                                          m_get_cmdline):
        """
        /var/run/scaleway exists.
        """
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, True),
            fake_cmdline=(m_get_cmdline, False)
        )
        self.assertTrue(DataSourceScaleway.on_scaleway())

    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('os.path.exists')
    @mock.patch('cloudinit.util.read_dmi_data')
    def test_on_scaleway_cmdline(self, m_read_dmi_data, m_file_exists,
                                 m_get_cmdline):
        """
        "scaleway" in /proc/cmdline.
        """
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, True)
        )
        self.assertTrue(DataSourceScaleway.on_scaleway())


def get_source_address_adapter(*args, **kwargs):
    """
    Scaleway user/vendor data API requires to be called with a privileged port.

    If the unittests are run as non-root, the user doesn't have the permission
    to bind on ports below 1024.

    This function removes the bind on a privileged address, since anyway the
    HTTP call is mocked by httpretty.
    """
    kwargs.pop('source_address')
    return requests.adapters.HTTPAdapter(*args, **kwargs)


class TestDataSourceScaleway(HttprettyTestCase):

    def setUp(self):
        tmp = self.tmp_dir()
        self.datasource = DataSourceScaleway.DataSourceScaleway(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': tmp})
        )
        super(TestDataSourceScaleway, self).setUp()

        self.metadata_url = \
            DataSourceScaleway.BUILTIN_DS_CONFIG['metadata_url']
        self.userdata_url = \
            DataSourceScaleway.BUILTIN_DS_CONFIG['userdata_url']
        self.vendordata_url = \
            DataSourceScaleway.BUILTIN_DS_CONFIG['vendordata_url']

    @mock.patch('cloudinit.sources.DataSourceScaleway.SourceAddressAdapter',
                get_source_address_adapter)
    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('time.sleep', return_value=None)
    def test_metadata_ok(self, sleep, m_get_cmdline):
        """
        get_data() returns metadata, user data and vendor data.
        """
        m_get_cmdline.return_value = 'scaleway'

        # Make user data API return a valid response
        httpretty.register_uri(httpretty.GET, self.metadata_url,
                               body=MetadataResponses.get_ok)
        httpretty.register_uri(httpretty.GET, self.userdata_url,
                               body=DataResponses.get_ok)
        httpretty.register_uri(httpretty.GET, self.vendordata_url,
                               body=DataResponses.get_ok)
        self.datasource.get_data()

        self.assertEqual(self.datasource.get_instance_id(),
                         MetadataResponses.FAKE_METADATA['id'])
        self.assertEqual(self.datasource.get_public_ssh_keys(), [
            elem['key'] for elem in
            MetadataResponses.FAKE_METADATA['ssh_public_keys']
        ])
        self.assertEqual(self.datasource.get_hostname(),
                         MetadataResponses.FAKE_METADATA['hostname'])
        self.assertEqual(self.datasource.get_userdata_raw(),
                         DataResponses.FAKE_USER_DATA)
        self.assertEqual(self.datasource.get_vendordata_raw(),
                         DataResponses.FAKE_USER_DATA)
        self.assertIsNone(self.datasource.availability_zone)
        self.assertIsNone(self.datasource.region)
        self.assertEqual(sleep.call_count, 0)

    @mock.patch('cloudinit.sources.DataSourceScaleway.SourceAddressAdapter',
                get_source_address_adapter)
    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('time.sleep', return_value=None)
    def test_metadata_404(self, sleep, m_get_cmdline):
        """
        get_data() returns metadata, but no user data nor vendor data.
        """
        m_get_cmdline.return_value = 'scaleway'

        # Make user and vendor data APIs return HTTP/404, which means there is
        # no user / vendor data for the server.
        httpretty.register_uri(httpretty.GET, self.metadata_url,
                               body=MetadataResponses.get_ok)
        httpretty.register_uri(httpretty.GET, self.userdata_url,
                               body=DataResponses.empty)
        httpretty.register_uri(httpretty.GET, self.vendordata_url,
                               body=DataResponses.empty)
        self.datasource.get_data()
        self.assertIsNone(self.datasource.get_userdata_raw())
        self.assertIsNone(self.datasource.get_vendordata_raw())
        self.assertEqual(sleep.call_count, 0)

    @mock.patch('cloudinit.sources.DataSourceScaleway.SourceAddressAdapter',
                get_source_address_adapter)
    @mock.patch('cloudinit.util.get_cmdline')
    @mock.patch('time.sleep', return_value=None)
    def test_metadata_rate_limit(self, sleep, m_get_cmdline):
        """
        get_data() is rate limited two times by the metadata API when fetching
        user data.
        """
        m_get_cmdline.return_value = 'scaleway'

        httpretty.register_uri(httpretty.GET, self.metadata_url,
                               body=MetadataResponses.get_ok)
        httpretty.register_uri(httpretty.GET, self.vendordata_url,
                               body=DataResponses.empty)

        httpretty.register_uri(
            httpretty.GET, self.userdata_url,
            responses=[
                httpretty.Response(body=DataResponses.rate_limited),
                httpretty.Response(body=DataResponses.rate_limited),
                httpretty.Response(body=DataResponses.get_ok),
            ]
        )
        self.datasource.get_data()
        self.assertEqual(self.datasource.get_userdata_raw(),
                         DataResponses.FAKE_USER_DATA)
        self.assertEqual(sleep.call_count, 2)
