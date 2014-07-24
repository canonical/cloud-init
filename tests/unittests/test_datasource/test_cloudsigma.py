# coding: utf-8
import copy

from cloudinit.cs_utils import Cepko
from cloudinit.sources import DataSourceCloudSigma

from .. import helpers as test_helpers


SERVER_CONTEXT = {
    "cpu": 1000,
    "cpus_instead_of_cores": False,
    "global_context": {"some_global_key": "some_global_val"},
    "mem": 1073741824,
    "meta": {
        "ssh_public_key": "ssh-rsa AAAAB3NzaC1yc2E.../hQ5D5 john@doe",
        "cloudinit-user-data": "#cloud-config\n\n...",
    },
    "name": "test_server",
    "requirements": [],
    "smp": 1,
    "tags": ["much server", "very performance"],
    "uuid": "65b2fb23-8c03-4187-a3ba-8b7c919e8890",
    "vnc_password": "9e84d6cb49e46379",
    "vendor_data": {
        "location": "zrh",
        "cloudinit": "#cloud-config\n\n...",
    }
}


class CepkoMock(Cepko):
    def __init__(self, mocked_context):
        self.result = mocked_context

    def all(self):
        return self


class DataSourceCloudSigmaTest(test_helpers.TestCase):
    def setUp(self):
        self.datasource = DataSourceCloudSigma.DataSourceCloudSigma("", "", "")
        self.datasource.is_running_in_cloudsigma = lambda: True
        self.datasource.cepko = CepkoMock(SERVER_CONTEXT)
        self.datasource.get_data()

    def test_get_hostname(self):
        self.assertEqual("test_server", self.datasource.get_hostname())
        self.datasource.metadata['name'] = ''
        self.assertEqual("65b2fb23", self.datasource.get_hostname())
        self.datasource.metadata['name'] = u'тест'
        self.assertEqual("65b2fb23", self.datasource.get_hostname())

    def test_get_public_ssh_keys(self):
        self.assertEqual([SERVER_CONTEXT['meta']['ssh_public_key']],
                         self.datasource.get_public_ssh_keys())

    def test_get_instance_id(self):
        self.assertEqual(SERVER_CONTEXT['uuid'],
                         self.datasource.get_instance_id())

    def test_metadata(self):
        self.assertEqual(self.datasource.metadata, SERVER_CONTEXT)

    def test_user_data(self):
        self.assertEqual(self.datasource.userdata_raw,
                         SERVER_CONTEXT['meta']['cloudinit-user-data'])

    def test_encoded_user_data(self):
        encoded_context = copy.deepcopy(SERVER_CONTEXT)
        encoded_context['meta']['base64_fields'] = 'cloudinit-user-data'
        encoded_context['meta']['cloudinit-user-data'] = 'aGkgd29ybGQK'
        self.datasource.cepko = CepkoMock(encoded_context)
        self.datasource.get_data()

        self.assertEqual(self.datasource.userdata_raw, b'hi world\n')

    def test_vendor_data(self):
        self.assertEqual(self.datasource.vendordata_raw,
                         SERVER_CONTEXT['vendor_data']['cloudinit'])

    def test_lack_of_vendor_data(self):
        stripped_context = copy.deepcopy(SERVER_CONTEXT)
        del stripped_context["vendor_data"]
        self.datasource = DataSourceCloudSigma.DataSourceCloudSigma("", "", "")
        self.datasource.cepko = CepkoMock(stripped_context)
        self.datasource.get_data()

        self.assertIsNone(self.datasource.vendordata_raw)

    def test_lack_of_cloudinit_key_in_vendor_data(self):
        stripped_context = copy.deepcopy(SERVER_CONTEXT)
        del stripped_context["vendor_data"]["cloudinit"]
        self.datasource = DataSourceCloudSigma.DataSourceCloudSigma("", "", "")
        self.datasource.cepko = CepkoMock(stripped_context)
        self.datasource.get_data()

        self.assertIsNone(self.datasource.vendordata_raw)
