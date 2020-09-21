# This is an example test file. It won't get merged

import pytest

from tests.integration_tests.platforms import (
    dynamic_client, OciClient, LxdContainerClient
)


CLOUD_CONFIG = """#cloud-config
bootcmd:
  - echo 'hello config!' > /tmp/cloud_config.txt"""


class TestSimple:
    @pytest.mark.cloud_config(CLOUD_CONFIG)
    def test_cloud_config(self, client):
        client.push_to_file('/home/ubuntu/my_test.txt', 'Hello world!')
        print(client.exec('cloud-init -v'))
        print(client.exec('cat /home/ubuntu/my_test.txt'))
        print(client.exec('cat /tmp/cloud_config.txt'))
        contents = client.pull_from_file('/home/ubuntu/my_test.txt')
        print(contents)

    @pytest.mark.lxd_container
    def test_lxd_client(self, client):
        print('I can only run on LXD')
        print(client.exec('cloud-init -v'))

    def test_dynamic(self, client):
        print('I can run anywhere')
        print(client.exec('cloud-init -v'))

    @pytest.mark.oci
    @pytest.mark.ec2
    def test_oci_and_ec2_client(self, client):
        print('I can only run on Oci and ec2')
        print(client.exec('cloud-init -v'))
