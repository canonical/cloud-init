# This file is part of cloud-init. See LICENSE file for license information.

"""Base Azure Cloud instance."""

from datetime import datetime, timedelta
from urllib.parse import urlparse
from time import sleep
import traceback
import os


# pylint: disable=no-name-in-module
from azure.storage.blob import BlockBlobService, BlobPermissions
from msrestazure.azure_exceptions import CloudError

from tests.cloud_tests import LOG

from ..instances import Instance


class AzureCloudInstance(Instance):
    """Azure Cloud backed instance."""

    platform_name = 'azurecloud'

    def __init__(self, platform, properties, config,
                 features, image_id, user_data=None):
        """Set up instance.

        @param platform: platform object
        @param properties: dictionary of properties
        @param config: dictionary of configuration values
        @param features: dictionary of supported feature flags
        @param image_id: image to find and/or use
        @param user_data: test user-data to pass to instance
        """
        super(AzureCloudInstance, self).__init__(
            platform, image_id, properties, config, features)

        self.ssh_port = 22
        self.ssh_ip = None
        self.instance = None
        self.image_id = image_id
        self.vm_name = 'ci-azure-i-%s' % self.platform.tag
        self.user_data = user_data
        self.ssh_key_file = os.path.join(
            platform.config['data_dir'], platform.config['private_key'])
        self.ssh_pubkey_file = os.path.join(
            platform.config['data_dir'], platform.config['public_key'])
        self.blob_client, self.container, self.blob = None, None, None

    def start(self, wait=True, wait_for_cloud_init=False):
        """Start instance with the platforms NIC."""
        if self.instance:
            return
        data = self.image_id.split('-')
        release, support = data[2].replace('_', '.'), data[3]
        sku = '%s-%s' % (release, support) if support == 'LTS' else release
        image_resource_id = '/subscriptions/%s' \
                            '/resourceGroups/%s' \
                            '/providers/Microsoft.Compute/images/%s' % (
                                self.platform.subscription_id,
                                self.platform.resource_group.name,
                                self.image_id)
        storage_uri = "http://%s.blob.core.windows.net" \
                      % self.platform.storage.name
        with open(self.ssh_pubkey_file, 'r') as key:
            ssh_pub_keydata = key.read()

        image_exists = False
        try:
            LOG.debug('finding image in resource group using image_id')
            self.platform.compute_client.images.get(
                self.platform.resource_group.name,
                self.image_id
            )
            image_exists = True
            LOG.debug('image found, launching instance, image_id=%s',
                      self.image_id)
        except CloudError:
            LOG.debug(('image not found, launching instance with base image, '
                       'image_id=%s'), self.image_id)

        vm_params = {
            'name': self.vm_name,
            'location': self.platform.location,
            'os_profile': {
                'computer_name': 'CI-%s' % self.platform.tag,
                'admin_username': self.ssh_username,
                "customData": self.user_data,
                "linuxConfiguration": {
                    "disable_password_authentication": True,
                    "ssh": {
                        "public_keys": [{
                            "path": "/home/%s/.ssh/authorized_keys" %
                                    self.ssh_username,
                            "keyData": ssh_pub_keydata
                        }]
                    }
                }
            },
            "diagnosticsProfile": {
                "bootDiagnostics": {
                    "storageUri": storage_uri,
                    "enabled": True
                }
            },
            'hardware_profile': {
                'vm_size': self.platform.vm_size
            },
            'storage_profile': {
                'image_reference': {
                    'id': image_resource_id
                } if image_exists else {
                    'publisher': 'Canonical',
                    'offer': 'UbuntuServer',
                    'sku': sku,
                    'version': 'latest'
                }
            },
            'network_profile': {
                'network_interfaces': [{
                    'id': self.platform.nic.id
                }]
            },
            'tags': {
                'Name': self.platform.tag,
            }
        }

        try:
            self.instance = self.platform.compute_client.virtual_machines.\
                create_or_update(self.platform.resource_group.name,
                                 self.vm_name, vm_params)
            LOG.debug('creating instance %s from image_id=%s', self.vm_name,
                      self.image_id)
        except CloudError as e:
            raise RuntimeError(
                'failed creating instance:\n{}'.format(traceback.format_exc())
            ) from e

        if wait:
            self.instance.wait()
            self.ssh_ip = self.platform.network_client.\
                public_ip_addresses.get(
                    self.platform.resource_group.name,
                    self.platform.public_ip.name
                ).ip_address
            self._wait_for_system(wait_for_cloud_init)

        self.instance = self.instance.result()
        self.blob_client, self.container, self.blob =\
            self._get_blob_client()

    def shutdown(self, wait=True):
        """Finds console log then stopping/deallocates VM"""
        LOG.debug('waiting on console log before stopping')
        attempts, exists = 5, False
        while not exists and attempts:
            try:
                attempts -= 1
                exists = self.blob_client.get_blob_to_bytes(
                    self.container, self.blob)
                LOG.debug('found console log')
            except Exception as e:
                if attempts:
                    LOG.debug('Unable to find console log, '
                              '%s attempts remaining', attempts)
                    sleep(15)
                else:
                    LOG.warning('Could not find console log: %s', e)

        LOG.debug('stopping instance %s', self.image_id)
        vm_deallocate = \
            self.platform.compute_client.virtual_machines.deallocate(
                self.platform.resource_group.name, self.image_id)
        if wait:
            vm_deallocate.wait()

    def destroy(self):
        """Delete VM and close all connections"""
        if self.instance:
            LOG.debug('destroying instance: %s', self.image_id)
            vm_delete = self.platform.compute_client.virtual_machines.delete(
                self.platform.resource_group.name, self.image_id)
            vm_delete.wait()

        self._ssh_close()

        super(AzureCloudInstance, self).destroy()

    def _execute(self, command, stdin=None, env=None):
        """Execute command on instance."""
        env_args = []
        if env:
            env_args = ['env'] + ["%s=%s" for k, v in env.items()]

        return self._ssh(['sudo'] + env_args + list(command), stdin=stdin)

    def _get_blob_client(self):
        """
        Use VM details to retrieve container and blob name.
        Then Create blob service client for sas token to
        retrieve console log.

        :return: blob service, container name, blob name
        """
        LOG.debug('creating blob service for console log')
        storage = self.platform.storage_client.storage_accounts.get_properties(
            self.platform.resource_group.name, self.platform.storage.name)

        keys = self.platform.storage_client.storage_accounts.list_keys(
            self.platform.resource_group.name, self.platform.storage.name
        ).keys[0].value

        virtual_machine = self.platform.compute_client.virtual_machines.get(
            self.platform.resource_group.name, self.instance.name,
            expand='instanceView')

        blob_uri = virtual_machine.instance_view.boot_diagnostics.\
            serial_console_log_blob_uri

        container, blob = urlparse(blob_uri).path.split('/')[-2:]

        blob_client = BlockBlobService(
            account_name=storage.name,
            account_key=keys)

        sas = blob_client.generate_blob_shared_access_signature(
            container_name=container, blob_name=blob, protocol='https',
            expiry=datetime.utcnow() + timedelta(hours=1),
            permission=BlobPermissions.READ)

        blob_client = BlockBlobService(
            account_name=storage.name,
            sas_token=sas)

        return blob_client, container, blob

    def console_log(self):
        """Instance console.

        @return_value: bytes of this instance’s console
        """
        boot_diagnostics = self.blob_client.get_blob_to_bytes(
            self.container, self.blob)
        return boot_diagnostics.content
