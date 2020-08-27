# This file is part of cloud-init. See LICENSE file for license information.

"""Base Azure Cloud class."""

import os
import base64
import traceback
from datetime import datetime
from tests.cloud_tests import LOG

# pylint: disable=no-name-in-module
from azure.common.credentials import ServicePrincipalCredentials
# pylint: disable=no-name-in-module
from azure.mgmt.resource import ResourceManagementClient
# pylint: disable=no-name-in-module
from azure.mgmt.network import NetworkManagementClient
# pylint: disable=no-name-in-module
from azure.mgmt.compute import ComputeManagementClient
# pylint: disable=no-name-in-module
from azure.mgmt.storage import StorageManagementClient
from msrestazure.azure_exceptions import CloudError

from .image import AzureCloudImage
from .instance import AzureCloudInstance
from ..platforms import Platform

from cloudinit import util as c_util


class AzureCloudPlatform(Platform):
    """Azure Cloud test platforms."""

    platform_name = 'azurecloud'

    def __init__(self, config):
        """Set up platform."""
        super(AzureCloudPlatform, self).__init__(config)
        self.tag = '%s-%s' % (
            config['tag'], datetime.now().strftime('%Y%m%d%H%M%S'))
        self.storage_sku = config['storage_sku']
        self.vm_size = config['vm_size']
        self.location = config['region']

        try:
            self.credentials, self.subscription_id = self._get_credentials()

            self.resource_client = ResourceManagementClient(
                self.credentials, self.subscription_id)
            self.compute_client = ComputeManagementClient(
                self.credentials, self.subscription_id)
            self.network_client = NetworkManagementClient(
                self.credentials, self.subscription_id)
            self.storage_client = StorageManagementClient(
                self.credentials, self.subscription_id)

            self.resource_group = self._create_resource_group()
            self.public_ip = self._create_public_ip_address()
            self.storage = self._create_storage_account(config)
            self.vnet = self._create_vnet()
            self.subnet = self._create_subnet()
            self.nic = self._create_nic()
        except CloudError as e:
            raise RuntimeError(
                'failed creating a resource:\n{}'.format(
                    traceback.format_exc()
                )
            ) from e

    def create_instance(self, properties, config, features,
                        image_id, user_data=None):
        """Create an instance

        @param properties: image properties
        @param config: image configuration
        @param features: image features
        @param image_id: string of image id
        @param user_data: test user-data to pass to instance
        @return_value: cloud_tests.instances instance
        """
        if user_data is not None:
            user_data = str(base64.b64encode(
                user_data.encode('utf-8')), 'utf-8')

        return AzureCloudInstance(self, properties, config, features,
                                  image_id, user_data)

    def get_image(self, img_conf):
        """Get image using specified image configuration.

        @param img_conf: configuration for image
        @return_value: cloud_tests.images instance
        """
        ss_region = self.azure_location_to_simplestreams_region()

        filters = [
            'arch=%s' % 'amd64',
            'endpoint=https://management.core.windows.net/',
            'region=%s' % ss_region,
            'release=%s' % img_conf['release']
        ]

        LOG.debug('finding image using streams')
        image = self._query_streams(img_conf, filters)

        try:
            image_id = image['id']
            LOG.debug('found image: %s', image_id)
            if image_id.find('__') > 0:
                image_id = image_id.split('__')[1]
                LOG.debug('image_id shortened to %s', image_id)
        except KeyError as e:
            raise RuntimeError(
                'no images found for %s' % img_conf['release']
            ) from e

        return AzureCloudImage(self, img_conf, image_id)

    def destroy(self):
        """Delete all resources in resource group."""
        LOG.debug("Deleting resource group: %s", self.resource_group.name)
        delete = self.resource_client.resource_groups.delete(
            self.resource_group.name)
        delete.wait()

    def azure_location_to_simplestreams_region(self):
        """Convert location to simplestreams region"""
        location = self.location.lower().replace(' ', '')
        LOG.debug('finding location %s using simple streams', location)
        regions_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'regions.json')
        region_simplestreams_map = c_util.load_json(
            c_util.load_file(regions_file))
        return region_simplestreams_map.get(location, location)

    def _get_credentials(self):
        """Get credentials from environment"""
        LOG.debug('getting credentials from environment')
        cred_file = os.path.expanduser('~/.azure/credentials.json')
        try:
            azure_creds = c_util.load_json(
                c_util.load_file(cred_file))
            subscription_id = azure_creds['subscriptionId']
            credentials = ServicePrincipalCredentials(
                client_id=azure_creds['clientId'],
                secret=azure_creds['clientSecret'],
                tenant=azure_creds['tenantId'])
            return credentials, subscription_id
        except KeyError as e:
            raise RuntimeError(
                'Please configure Azure service principal'
                ' credentials in %s' % cred_file
            ) from e

    def _create_resource_group(self):
        """Create resource group"""
        LOG.debug('creating resource group')
        resource_group_name = self.tag
        resource_group_params = {
            'location': self.location
        }
        resource_group = self.resource_client.resource_groups.create_or_update(
            resource_group_name, resource_group_params)
        return resource_group

    def _create_storage_account(self, config):
        LOG.debug('creating storage account')
        storage_account_name = 'storage%s' % datetime.now().\
            strftime('%Y%m%d%H%M%S')
        storage_params = {
            'sku': {
                'name': config['storage_sku']
            },
            'kind': "Storage",
            'location': self.location
        }
        storage_account = self.storage_client.storage_accounts.create(
            self.resource_group.name, storage_account_name, storage_params)
        return storage_account.result()

    def _create_public_ip_address(self):
        """Create public ip address"""
        LOG.debug('creating public ip address')
        public_ip_name = '%s-ip' % self.resource_group.name
        public_ip_params = {
            'location': self.location,
            'public_ip_allocation_method': 'Dynamic'
        }
        ip = self.network_client.public_ip_addresses.create_or_update(
            self.resource_group.name, public_ip_name, public_ip_params)
        return ip.result()

    def _create_vnet(self):
        """create virtual network"""
        LOG.debug('creating vnet')
        vnet_name = '%s-vnet' % self.resource_group.name
        vnet_params = {
            'location': self.location,
            'address_space': {
                'address_prefixes': ['10.0.0.0/16']
            }
        }
        vnet = self.network_client.virtual_networks.create_or_update(
            self.resource_group.name, vnet_name, vnet_params)
        return vnet.result()

    def _create_subnet(self):
        """create sub-network"""
        LOG.debug('creating subnet')
        subnet_name = '%s-subnet' % self.resource_group.name
        subnet_params = {
            'address_prefix': '10.0.0.0/24'
        }
        subnet = self.network_client.subnets.create_or_update(
            self.resource_group.name, self.vnet.name,
            subnet_name, subnet_params)
        return subnet.result()

    def _create_nic(self):
        """Create network interface controller"""
        LOG.debug('creating nic')
        nic_name = '%s-nic' % self.resource_group.name
        nic_params = {
            'location': self.location,
            'ip_configurations': [{
                'name': 'ipconfig',
                'subnet': {
                    'id': self.subnet.id
                },
                'publicIpAddress': {
                    'id': "/subscriptions/%s"
                          "/resourceGroups/%s/providers/Microsoft.Network"
                          "/publicIPAddresses/%s" % (
                              self.subscription_id, self.resource_group.name,
                              self.public_ip.name),
                }
            }]
        }
        nic = self.network_client.network_interfaces.create_or_update(
            self.resource_group.name, nic_name, nic_params)
        return nic.result()
