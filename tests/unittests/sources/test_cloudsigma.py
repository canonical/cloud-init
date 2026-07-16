# This file is part of cloud-init. See LICENSE file for license information.


import copy
from unittest import mock

import pytest

from cloudinit import distros, importer, sources
from cloudinit.sources import DataSourceCloudSigma
from cloudinit.sources.helpers.cloudsigma import Cepko

SERVER_CONTEXT = {
    "cpu": 1000,
    "cpus_instead_of_cores": False,
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
    },
}

DS_PATH = "cloudinit.sources.DataSourceCloudSigma.DataSourceCloudSigma"


class CepkoMock(Cepko):
    def __init__(self, mocked_context):
        self.result = mocked_context

    def all(self):
        return self


@pytest.fixture
def ds(mocker, paths):
    mocker.patch(DS_PATH + ".override_ds_detect", return_value=True)
    distro_cls = distros.fetch("ubuntu")
    distro = distro_cls("ubuntu", cfg={}, paths=paths)
    datasource = DataSourceCloudSigma.DataSourceCloudSigma(
        sys_cfg={}, distro=distro, paths=paths
    )
    datasource.cepko = CepkoMock(SERVER_CONTEXT)
    return datasource


class TestDataSourceCloudSigma:

    def test_get_hostname(self, ds):
        ds.get_data()
        assert "test_server" == ds.get_hostname().hostname
        ds.metadata["name"] = ""
        assert "65b2fb23" == ds.get_hostname().hostname
        utf8_hostname = b"\xd1\x82\xd0\xb5\xd1\x81\xd1\x82".decode("utf-8")
        ds.metadata["name"] = utf8_hostname
        assert "65b2fb23" == ds.get_hostname().hostname

    def test_get_public_ssh_keys(self, ds):
        ds.get_data()
        assert [
            SERVER_CONTEXT["meta"]["ssh_public_key"]
        ] == ds.get_public_ssh_keys()

    def test_get_instance_id(self, ds):
        ds.get_data()
        assert SERVER_CONTEXT["uuid"] == ds.get_instance_id()

    def test_platform(self, ds):
        """All platform-related attributes are set."""
        ds.get_data()
        assert ds.cloud_name == "cloudsigma"
        assert ds.platform_type == "cloudsigma"
        assert ds.subplatform == "cepko (/dev/ttyS1)"

    def test_metadata(self, ds):
        ds.get_data()
        assert ds.metadata == SERVER_CONTEXT

    def test_user_data(self, ds):
        ds.get_data()
        assert ds.userdata_raw == SERVER_CONTEXT["meta"]["cloudinit-user-data"]

    def test_encoded_user_data(self, ds):
        encoded_context = copy.deepcopy(SERVER_CONTEXT)
        encoded_context["meta"]["base64_fields"] = "cloudinit-user-data"
        encoded_context["meta"]["cloudinit-user-data"] = "aGkgd29ybGQK"
        ds.cepko = CepkoMock(encoded_context)
        ds.get_data()

        assert ds.userdata_raw == b"hi world\n"

    def test_vendor_data(self, ds):
        ds.get_data()
        assert ds.vendordata_raw == SERVER_CONTEXT["vendor_data"]["cloudinit"]

    def test_lack_of_vendor_data(self, ds):
        stripped_context = copy.deepcopy(SERVER_CONTEXT)
        del stripped_context["vendor_data"]
        ds.cepko = CepkoMock(stripped_context)
        ds.get_data()

        assert ds.vendordata_raw is None

    def test_lack_of_cloudinit_key_in_vendor_data(self, ds):
        stripped_context = copy.deepcopy(SERVER_CONTEXT)
        del stripped_context["vendor_data"]["cloudinit"]
        ds.cepko = CepkoMock(stripped_context)
        ds.get_data()

        assert ds.vendordata_raw is None


class TestDsLoads:
    def test_get_datasource_list_returns_in_local(self):
        deps = (sources.DEP_FILESYSTEM,)
        ds_list = DataSourceCloudSigma.get_datasource_list(deps)
        assert ds_list == [DataSourceCloudSigma.DataSourceCloudSigma]

    @mock.patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    def test_list_sources_finds_ds(self):
        found = sources.list_sources(
            ["CloudSigma"],
            (sources.DEP_FILESYSTEM,),
            ["cloudinit.sources"],
        )
        assert [DataSourceCloudSigma.DataSourceCloudSigma] == found
