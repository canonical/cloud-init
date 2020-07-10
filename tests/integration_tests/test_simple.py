import pytest

from tests.integration_tests.platforms import (
    dynamic_client, OracleClient, LxdContainerClient
)


class TestSimple:
    @pytest.mark.lxd_container
    def test_lxd_client(self):
        with LxdContainerClient() as client:
            print('I can only run on LXD')
            print(client.exec('cloud-init -v'))

    def test_dynamic(self):
        with dynamic_client() as client:
            print('I can run anywhere')
            print(client.exec('cloud-init -v'))

    @pytest.mark.oracle
    def test_oracle_client(self):
        with OracleClient() as client:
            print('I can only run on Oracle')
            print(client.exec('cloud-init -v'))
