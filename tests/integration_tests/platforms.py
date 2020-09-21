# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC, abstractmethod
import os
from tempfile import NamedTemporaryFile

from pycloudlib import EC2, GCE, Azure, OCI, LXD
from pycloudlib.cloud import BaseCloud
from pycloudlib.instance import BaseInstance

import cloudinit
from cloudinit.subp import subp
from tests.integration_tests import integration_settings

try:
    from typing import Callable, Optional
except ImportError:
    pass

current_image = None


def set_current_image(image):
    global current_image
    current_image = image


class IntegrationClient(ABC):
    client = None  # type: Optional[BaseCloud]
    instance = None  # type: Optional[BaseInstance]
    datasource = None  # type: Optional[str]
    use_sudo = True

    def __init__(self, user_data=None, instance_type=None, wait=True,
                 settings=integration_settings, launch_kwargs=None):
        self.user_data = user_data
        self.instance_type = settings.INSTANCE_TYPE if \
            instance_type is None else instance_type
        self.wait = wait
        self.settings = settings
        self.launch_kwargs = launch_kwargs if launch_kwargs else {}
        self.client = self._get_client()

    @abstractmethod
    def _get_client(self):
        raise NotImplementedError

    def _get_image(self):
        if current_image:
            return current_image
        image_id = self.settings.OS_IMAGE
        try:
            image_id = self.client.released_image(self.settings.OS_IMAGE)
        except (ValueError, IndexError):
            pass
        return image_id

    def launch(self):
        if self.settings.EXISTING_INSTANCE_ID:
            print('Not launching instance due to EXISTING_INSTANCE_ID. '
                  'Instance id: {}'.format(self.settings.EXISTING_INSTANCE_ID))
            self.instance = self.client.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            return
        image_id = self._get_image()
        launch_args = {
            'image_id': image_id,
            'user_data': self.user_data,
            'wait': self.wait,
        }
        if self.instance_type:
            launch_args['instance_type'] = self.instance_type
        launch_args.update(self.launch_kwargs)
        self.instance = self.client.launch(**launch_args)
        print('Launched instance: {}'.format(self.instance))

    def destroy(self):
        self.instance.delete()

    def exec(self, command):
        return self.instance.execute(command)

    def pull_file(self, remote_file, local_file):
        self.instance.pull_file(remote_file, local_file)

    def push_file(self, local_path, remote_path):
        self.instance.push_file(local_path, remote_path)

    def pull_from_file(self, remote_path) -> str:
        tmp_file = NamedTemporaryFile('r')
        self.pull_file(remote_path, tmp_file.name)
        with tmp_file as f:
            contents = f.read()
        return contents

    def push_to_file(self, remote_path, contents: str):
        with NamedTemporaryFile('w', delete=False) as tmp_file:
            tmp_file.write(contents)
        self.push_file(tmp_file.name, remote_path)
        os.unlink(tmp_file.name)

    def snapshot(self):
        return self.client.snapshot(self.instance, clean=True)

    def _install_new_cloud_init(self, remote_script):
        self.exec(remote_script)
        version = self.exec('cloud-init -v').split()[-1]
        print('Installed cloud-init version: {}'.format(version))
        self.instance.clean()
        image_id = self.snapshot()
        print('Created new image: {}'.format(image_id))
        set_current_image(image_id)
        # self.instance.restart(wait=True)

    def install_proposed_image(self):
        print('Installing proposed image')
        remote_script = (
            '{sudo} echo deb "http://archive.ubuntu.com/ubuntu '
            '$(lsb_release -sc)-proposed main" | '
            '{sudo} tee /etc/apt/sources.list.d/proposed.list\n'
            '{sudo} apt-get update -q\n'
            '{sudo} apt-get install -qy cloud-init'
        ).format(sudo='sudo' if self.use_sudo else '')
        self._install_new_cloud_init(remote_script)

    def install_ppa(self):
        print('Installing PPA')
        remote_script = (
            '{sudo} add-apt-repository ppa:cloud-init-dev/proposed -y && '
            '{sudo} apt-get update -q && '
            '{sudo} apt-get install -qy cloud-init'
        ).format(sudo='sudo' if self.use_sudo else '')
        self._install_new_cloud_init(remote_script)

    def install_deb(self):
        print('Installing deb package')
        deb_path = integration_settings.IMAGE_SOURCE
        deb_name = os.path.basename(deb_path)
        remote_path = '/tmp/{}'.format(deb_name)
        self.push_file(
            local_path=integration_settings.IMAGE_SOURCE,
            remote_path=remote_path)
        remote_script = '{sudo} dpkg -i {path}'.format(
            sudo='sudo' if self.use_sudo else '', path=remote_path)
        self._install_new_cloud_init(remote_script)

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()


class Ec2Client(IntegrationClient):
    datasource = 'ec2'

    def _get_client(self):
        return EC2(tag='ec2-integration-test')


class GceClient(IntegrationClient):
    datasource = 'gce'

    def _get_client(self):
        return GCE(
            tag='gce-integration-test',
            project=self.settings.GCE_PROJECT,
            region=self.settings.GCE_REGION,
            zone=self.settings.GCE_ZONE,
        )


class AzureClient(IntegrationClient):
    datasource = 'azure'

    def _get_client(self):
        return Azure(tag='azure-integration-test')


class OciClient(IntegrationClient):
    datasource = 'oci'

    def _get_client(self):
        return OCI(
            tag='oci-integration-test',
            compartment_id=self.settings.OCI_COMPARTMENT_ID
        )


class LxdContainerClient(IntegrationClient):
    datasource = 'lxd_container'
    use_sudo = False

    def _get_client(self):
        return LXD(tag='lxd-integration-test')

    def _mount_source(self):
        command = (
            'lxc config device add {name} host-cloud-init disk '
            'source={cloudinit_path} '
            'path=/usr/lib/python3/dist-packages/cloudinit'
        ).format(
            name=self.instance.name, cloudinit_path=cloudinit.__path__[0])
        subp(command.split())

    def launch(self):
        super().launch()
        if self.settings.IMAGE_SOURCE == 'IN_PLACE':
            self._mount_source()


client_name_to_class = {
    'ec2': Ec2Client,
    'gce': GceClient,
    # 'azure': AzureClient,  # Not supported yet
    'oci': OciClient,
    'lxd_container': LxdContainerClient
}

try:
    dynamic_client = client_name_to_class[
        integration_settings.PLATFORM
    ]  # type: Callable[..., IntegrationClient]
except KeyError:
    raise ValueError(
        "{} is an invalid PLATFORM specified in settings. "
        "Must be one of {}".format(
            integration_settings.PLATFORM, client_name_to_class.keys()
        )
    )
