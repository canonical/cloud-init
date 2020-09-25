# This is an example test file. It won't get merged

import pytest

from tests.integration_tests.platforms import (
    dynamic_client, OciClient, LxdContainerClient
)


USER_DATA = """#cloud-config
bootcmd:
  - echo 'hello config!' > /tmp/user_data.txt"""


class TestSimple:
    @pytest.mark.user_data(USER_DATA)
    def test_cloud_config(self, client):
        client.push_to_file('/home/ubuntu/my_test.txt', 'Hello world!')
        print(client.exec('cloud-init -v'))
        print(client.exec('cat /home/ubuntu/my_test.txt'))
        print(client.exec('cat /tmp/user_data.txt'))
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


class TestSingleInstance:
    # Since we're using the class_client here, everything in this class
    # will run on the same cloud instance
    def test_one(self, class_client):
        print('I will (probably) get run first')
        print(class_client.exec('cloud-init -v'))

    def test_two(self, class_client):
        print('No setup for me!')
        print(class_client.exec('cloud-init -v'))
