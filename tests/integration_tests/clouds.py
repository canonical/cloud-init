# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC, abstractmethod

from pycloudlib import EC2, GCE, Azure, OCI, LXD

from tests.integration_tests import integration_settings


class IntegrationCloud(ABC):
    def __init__(self, settings=integration_settings):
        self.settings = settings
        self.cloud_instance = self._get_cloud_instance()
        self.image_id = self._get_initial_image()

    @abstractmethod
    def _get_cloud_instance(self):
        raise NotImplementedError

    def _get_initial_image(self):
        image_id = self.settings.OS_IMAGE
        try:
            image_id = self.cloud_instance.released_image(
                self.settings.OS_IMAGE)
        except (ValueError, IndexError):
            pass
        return image_id

    def destroy(self):
        pass

    def snapshot(self, instance):
        return self.cloud_instance.snapshot(instance, clean=True)


class Ec2Cloud(IntegrationCloud):
    def _get_cloud_instance(self):
        return EC2(tag='ec2-integration-test')


class GceCloud(IntegrationCloud):
    def _get_cloud_instance(self):
        return GCE(
            tag='gce-integration-test',
            project=self.settings.GCE_PROJECT,
            region=self.settings.GCE_REGION,
            zone=self.settings.GCE_ZONE,
        )


class AzureCloud(IntegrationCloud):
    def _get_cloud_instance(self):
        return Azure(tag='azure-integration-test')

    def destroy(self):
        super()
        self.cloud_instance.delete_resource_group()


class OciCloud(IntegrationCloud):
    def _get_cloud_instance(self):
        return OCI(
            tag='oci-integration-test',
            compartment_id=self.settings.OCI_COMPARTMENT_ID
        )


class LxdContainerCloud(IntegrationCloud):
    def _get_cloud_instance(self):
        return LXD(tag='lxd-integration-test')
