# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC, abstractmethod
import logging

from pycloudlib import EC2, GCE, Azure, OCI, LXD

import cloudinit
from cloudinit.subp import subp
from tests.integration_tests import integration_settings
from tests.integration_tests.instances import (
    IntegrationEc2Instance,
    IntegrationGceInstance,
    IntegrationAzureInstance, IntegrationInstance,
    IntegrationOciInstance,
    IntegrationLxdContainerInstance,
)

try:
    from typing import Optional
except ImportError:
    pass


log = logging.getLogger('integration_testing')


class IntegrationCloud(ABC):
    datasource = None  # type: Optional[str]
    integration_instance_cls = IntegrationInstance

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

    def _perform_launch(self, launch_kwargs):
        pycloudlib_instance = self.cloud_instance.launch(**launch_kwargs)
        pycloudlib_instance.wait(raise_on_cloudinit_failure=False)
        return pycloudlib_instance

    def launch(self, user_data=None, launch_kwargs=None,
               settings=integration_settings):
        if self.settings.EXISTING_INSTANCE_ID:
            log.info(
                'Not launching instance due to EXISTING_INSTANCE_ID. '
                'Instance id: %s', self.settings.EXISTING_INSTANCE_ID)
            self.instance = self.cloud_instance.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            return
        kwargs = {
            'image_id': self.image_id,
            'user_data': user_data,
            'wait': False,
        }
        if launch_kwargs:
            kwargs.update(launch_kwargs)
        log.info(
            "Launching instance with launch_kwargs:\n{}".format(
                "\n".join("{}={}".format(*item) for item in kwargs.items())
            )
        )

        pycloudlib_instance = self._perform_launch(kwargs)

        log.info('Launched instance: %s', pycloudlib_instance)
        return self.get_instance(pycloudlib_instance, settings)

    def get_instance(self, cloud_instance, settings=integration_settings):
        return self.integration_instance_cls(self, cloud_instance, settings)

    def destroy(self):
        pass

    def snapshot(self, instance):
        return self.cloud_instance.snapshot(instance, clean=True)


class Ec2Cloud(IntegrationCloud):
    datasource = 'ec2'
    integration_instance_cls = IntegrationEc2Instance

    def _get_cloud_instance(self):
        return EC2(tag='ec2-integration-test')


class GceCloud(IntegrationCloud):
    datasource = 'gce'
    integration_instance_cls = IntegrationGceInstance

    def _get_cloud_instance(self):
        return GCE(
            tag='gce-integration-test',
            project=self.settings.GCE_PROJECT,
            region=self.settings.GCE_REGION,
            zone=self.settings.GCE_ZONE,
        )


class AzureCloud(IntegrationCloud):
    datasource = 'azure'
    integration_instance_cls = IntegrationAzureInstance

    def _get_cloud_instance(self):
        return Azure(tag='azure-integration-test')

    def destroy(self):
        self.cloud_instance.delete_resource_group()


class OciCloud(IntegrationCloud):
    datasource = 'oci'
    integration_instance_cls = IntegrationOciInstance

    def _get_cloud_instance(self):
        return OCI(
            tag='oci-integration-test',
            compartment_id=self.settings.OCI_COMPARTMENT_ID
        )


class LxdContainerCloud(IntegrationCloud):
    datasource = 'lxd_container'
    integration_instance_cls = IntegrationLxdContainerInstance

    def _get_cloud_instance(self):
        return LXD(tag='lxd-integration-test')

    def _perform_launch(self, launch_kwargs):
        launch_kwargs['inst_type'] = launch_kwargs.pop('instance_type', None)
        launch_kwargs.pop('wait')

        pycloudlib_instance = self.cloud_instance.init(
            launch_kwargs.pop('name', None),
            launch_kwargs.pop('image_id'),
            **launch_kwargs
        )
        if self.settings.CLOUD_INIT_SOURCE == 'IN_PLACE':
            self._mount_source(pycloudlib_instance)
        pycloudlib_instance.start(wait=False)
        pycloudlib_instance.wait(raise_on_cloudinit_failure=False)
        return pycloudlib_instance

    def _mount_source(self, instance):
        container_path = '/usr/lib/python3/dist-packages/cloudinit'
        format_variables = {
            'name': instance.name,
            'cloudinit_path': cloudinit.__path__[0],
            'container_path': container_path,
        }
        log.info(
            'Mounting source {cloudinit_path} directly onto LXD container/vm '
            'named {name} at {container_path}'.format(**format_variables))
        command = (
            'lxc config device add {name} host-cloud-init disk '
            'source={cloudinit_path} '
            'path={container_path}'
        ).format(**format_variables)
        subp(command.split())
